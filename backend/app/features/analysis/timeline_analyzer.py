"""Timeline data generation and cache management.

Bins per-topic message density from MCAP files and produces the rendering
data for the timeline horizontal heatmap and the Loss Rate chart.
Also exposes per-message lookups used by the rug plot.
"""

import json
import logging
import math
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from app.features.analysis.mcap_analyzer import _read_mcap
from app.features.analysis.schemas import (
    MessageDetailItem,
    MessagesDetailResponse,
    TimelineBin,
    TimelineData,
    TimelineGap,
    TimelineTopic,
)
from app.infra.mcap import MCAPReader, find_mcap_files, resolve_timestamp_sec
from app.settings import get_settings

logger = logging.getLogger(__name__)

# Target range for bin count
_MIN_BINS = 600
_MAX_BINS = 1800

# Cache file name
_CACHE_FILENAME = "timeline_data.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_timeline(directory: Path) -> TimelineData | None:
    """Load the cached timeline_data.json."""
    cache_path = directory / _CACHE_FILENAME
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return TimelineData.model_validate(data)
    except (json.JSONDecodeError, ValueError, OSError, ValidationError) as e:
        logger.warning("Failed to load timeline data: %s (%s)", cache_path, e)
        return None


def build_and_save_timeline(directory: Path) -> TimelineData:  # pragma: no cover
    """Build timeline data from MCAP and persist it to the cache file."""
    mcap_files = find_mcap_files(directory)
    if not mcap_files:
        raise FileNotFoundError(f"MCAP file not found: {directory}")

    mcap_path = mcap_files[0]

    # Fast-read the minimum log_time from the summary (used as the rug plot time-filter origin)
    with MCAPReader(mcap_path) as reader:
        log_time_min_ns, _ = reader.get_time_range_ns()

    topic_timestamps, _topic_sizes, topic_types, _stamp_sources = _read_mcap(mcap_path)
    data = _build_timeline(
        topic_timestamps,
        topic_types,
        log_time_min_ns=log_time_min_ns,
        resolve_expected_hz=get_settings().recording.resolve_expected_hz,
    )

    cache_path = directory / _CACHE_FILENAME
    cache_path.write_text(
        json.dumps(data.model_dump(), ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved timeline data: %s", cache_path)
    return data


def read_messages_in_range(  # pragma: no cover
    directory: Path,
    topic: str,
    from_sec: float,
    to_sec: float,
) -> MessagesDetailResponse:
    """Read messages from MCAP within the specified range (used for rug plots).

    The time range is specified in seconds relative to the recording start.
    Uses the mcap library's `iter_decoded_messages(topics=, start_time=, end_time=)`
    for chunk-level time + topic filtering, which keeps large MCAPs fast.

    recording_start_ns is taken from the cached timeline_data.json when
    available. Otherwise, the minimum log_time from the MCAP summary is used
    as a fast fallback (relative coordinates against the timeline can differ
    by tens of milliseconds in that case).
    """
    mcap_files = find_mcap_files(directory)
    if not mcap_files:
        raise FileNotFoundError(f"MCAP file not found: {directory}")

    mcap_path = mcap_files[0]

    # Resolve recording start time, expected_hz, and log_time_offset (cache first)
    recording_start_ns, expected_hz, log_time_offset_ns = _resolve_timeline_meta(directory, topic, mcap_path)
    if recording_start_ns == 0:
        # Edge case where the MCAP has no statistics
        return MessagesDetailResponse(topic=topic, expected_hz=expected_hz, messages=[])

    recording_start_sec = recording_start_ns / 1e9

    # log_time filter: the chunk index uses log_time, so convert from header.stamp-based
    # recording_start_ns by adding log_time_offset. Add a 1 second margin to absorb
    # jitter and per-message offsets.
    margin_ns = int(1.0 * 1e9)
    filter_anchor_ns = recording_start_ns + log_time_offset_ns
    start_filter_ns = max(0, filter_anchor_ns + int(from_sec * 1e9) - margin_ns)
    end_filter_ns = filter_anchor_ns + int(to_sec * 1e9) + margin_ns

    messages: list[MessageDetailItem] = []
    with MCAPReader(mcap_path) as reader:
        for i, msg in enumerate(
            reader.iter_messages(
                topics=[topic],
                start_time_ns=start_filter_ns,
                end_time_ns=end_filter_ns,
            )
        ):
            ts_sec = resolve_timestamp_sec(msg.decoded, msg.timestamp_ns)
            relative = ts_sec - recording_start_sec
            if from_sec <= relative <= to_sec:
                messages.append(
                    MessageDetailItem(
                        index=i,
                        timestamp_sec=round(relative, 6),
                        size_bytes=msg.size_bytes,
                    )
                )

    # On cache-less fallback, estimate expected_hz from the loaded samples
    if expected_hz == 0.0 and len(messages) >= 2:
        ts_list = [m.timestamp_sec for m in messages]
        expected_hz = _estimate_hz(ts_list)

    return MessagesDetailResponse(
        topic=topic,
        expected_hz=expected_hz,
        messages=messages,
    )


def _resolve_timeline_meta(  # pragma: no cover
    directory: Path,
    topic: str,
    mcap_path: Path,
) -> tuple[int, float, int]:
    """Resolve recording_start_ns / expected_hz / log_time_offset_ns for the rug plot.

    Uses the cache (timeline_data.json) when available; otherwise reads only
    the start of log_time from the MCAP summary (in that case
    recording_start_ns = log_time_min and log_time_offset_ns = 0).
    """
    cached = load_timeline(directory)
    if cached and cached.recording_start_ns:
        topic_data = next((t for t in cached.topics if t.name == topic), None)
        expected_hz = topic_data.expected_hz if topic_data else 0.0
        return cached.recording_start_ns, expected_hz, cached.log_time_offset_ns

    # Fallback: read the minimum log_time from the MCAP summary (~6ms)
    with MCAPReader(mcap_path) as reader:
        start_ns, _ = reader.get_time_range_ns()
        if start_ns > 0:
            return start_ns, 0.0, 0
    return 0, 0.0, 0


# ---------------------------------------------------------------------------
# Private: binning
# ---------------------------------------------------------------------------

# Standard values used for automatic frequency estimation (same as models.py)
_STANDARD_FREQUENCIES = [10, 15, 20, 25, 30, 50, 60, 100, 120, 200, 500]


def _estimate_hz(timestamps: list[float]) -> float:
    """Estimate the nearest standard frequency from a list of timestamps."""
    if len(timestamps) < 2:
        return 0.0
    sorted_ts = sorted(timestamps)
    intervals = [sorted_ts[i + 1] - sorted_ts[i] for i in range(len(sorted_ts) - 1)]
    intervals.sort()
    median = intervals[len(intervals) // 2]
    if median <= 0:
        return 0.0
    actual_hz = 1.0 / median
    return float(min(_STANDARD_FREQUENCIES, key=lambda f: abs(f - actual_hz)))


def _calc_bin_width(duration_sec: float) -> float:
    """Choose a bin width based on recording duration so the count stays within 600-1800 bins."""
    if duration_sec <= 0:
        return 1.0

    nice_widths = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
    best = nice_widths[0]
    for w in nice_widths:
        num_bins = duration_sec / w
        if _MIN_BINS <= num_bins <= _MAX_BINS:
            best = w
            break
        if num_bins < _MIN_BINS:
            break
        best = w

    return best


def _build_timeline(
    topic_timestamps: dict[str, list[float]],
    topic_types: dict[str, str],
    log_time_min_ns: int = 0,
    resolve_expected_hz: Callable[[str], float | None] | None = None,
) -> TimelineData:
    """Build timeline data from a topic-to-timestamps dictionary.

    log_time_min_ns: minimum log_time in the MCAP (ns).
        The diff against recording_start_ns (header.stamp based) is stored as
        log_time_offset_ns and used as the log_time filter origin when the
        rug plot scans the MCAP.
    resolve_expected_hz: resolves the config-declared expected Hz
        (RECORDING_CONFIG expected_hz_patterns) for a topic name. When it
        returns a value, that value overrides the auto-estimated expected Hz
        for that topic (matching the quality report).
    """
    all_ts: list[float] = []
    for ts_list in topic_timestamps.values():
        all_ts.extend(ts_list)

    if not all_ts:
        return TimelineData(
            duration_sec=0,
            bin_width_sec=1.0,
            recording_start_ns=0,
            log_time_offset_ns=0,
            topics=[],
        )

    recording_start = min(all_ts)
    recording_end = max(all_ts)
    duration_sec = recording_end - recording_start

    bin_width = _calc_bin_width(duration_sec)
    num_bins = max(1, math.ceil(duration_sec / bin_width))

    topics: list[TimelineTopic] = []
    for topic_name in sorted(topic_timestamps.keys()):
        timestamps = sorted(topic_timestamps[topic_name])
        # A config-declared expected Hz wins; otherwise estimate from the data.
        config_hz = resolve_expected_hz(topic_name) if resolve_expected_hz else None
        expected_hz = config_hz if config_hz is not None and config_hz > 0 else _estimate_hz(timestamps)
        msg_type = topic_types.get(topic_name, "unknown")

        # Binning (keep expected as float; rounding introduces quantization noise)
        bins: list[TimelineBin] = []
        expected_per_bin = max(0.1, expected_hz * bin_width)

        # IQR-based loss event detection (also catches single lost frames)
        expected_interval = 1.0 / expected_hz if expected_hz > 0 else 0.0
        loss_events = _detect_loss_events_for_timeline(timestamps, expected_interval, recording_start)

        # Also include start/end empty intervals as losses
        if timestamps and expected_interval > 0:
            edge_events = _detect_edge_loss_for_timeline(
                first_ts_rel=timestamps[0] - recording_start,
                last_ts_rel=timestamps[-1] - recording_start,
                duration_sec=duration_sec,
                expected_interval=expected_interval,
            )
            # Sort by ascending timestamp (= start_delay -> middle gaps -> end_early)
            loss_events = sorted(edge_events + loss_events, key=lambda le: le[0])

        # Build TimelineGap from loss_events (with severity)
        gaps: list[TimelineGap] = []
        for le_ts, le_dur, le_sev in loss_events:
            lost = max(0, round(le_dur / expected_interval) - 1) if expected_interval > 0 else 0
            gaps.append(
                TimelineGap(
                    start_sec=round(le_ts, 3),
                    end_sec=round(le_ts + le_dur, 3),
                    duration_sec=round(le_dur, 4),
                    lost_count=lost,
                    severity=le_sev,
                )
            )

        for i in range(num_bins):
            bin_start = recording_start + i * bin_width
            bin_end = bin_start + bin_width
            count = sum(1 for ts in timestamps if bin_start <= ts < bin_end)
            bin_t = i * bin_width
            # Determine the loss level inside the bin using LossEvent
            bin_has_gap = False
            bin_has_minor = False
            for le_ts, le_dur, le_sev in loss_events:
                le_end = le_ts + le_dur
                if le_end > bin_t and le_ts < bin_t + bin_width:
                    if le_sev == "major":
                        bin_has_gap = True
                    else:
                        bin_has_minor = True
            bins.append(
                TimelineBin(
                    t=round(bin_t, 3),
                    count=count,
                    expected=round(expected_per_bin, 2),
                    has_gap=bin_has_gap,
                    has_minor_loss=bin_has_minor,
                )
            )

        topics.append(
            TimelineTopic(
                name=topic_name,
                msg_type=msg_type,
                expected_hz=expected_hz,
                bins=bins,
                gaps=gaps,
            )
        )

    recording_start_ns = int(recording_start * 1e9)
    log_time_offset_ns = log_time_min_ns - recording_start_ns if log_time_min_ns > 0 else 0

    return TimelineData(
        duration_sec=round(duration_sec, 2),
        bin_width_sec=bin_width,
        recording_start_ns=recording_start_ns,
        log_time_offset_ns=log_time_offset_ns,
        topics=topics,
    )


def _detect_edge_loss_for_timeline(
    *,
    first_ts_rel: float,
    last_ts_rel: float,
    duration_sec: float,
    expected_interval: float,
) -> list[tuple[float, float, str]]:
    """Detect start/end empty intervals as loss events (lightweight version for timelines)."""
    if expected_interval <= 0:
        return []

    events: list[tuple[float, float, str]] = []
    threshold = expected_interval * 1.5

    # Loss at the start
    if first_ts_rel > threshold:
        lost = max(0, round(first_ts_rel / expected_interval) - 1)
        if lost > 0:
            severity = "major" if lost >= 3 else "minor"
            events.append((0.0, first_ts_rel, severity))

    # Loss at the end
    end_gap = duration_sec - last_ts_rel
    if end_gap > threshold:
        lost = max(0, round(end_gap / expected_interval) - 1)
        if lost > 0:
            severity = "major" if lost >= 3 else "minor"
            events.append((last_ts_rel, end_gap, severity))

    return events


def _detect_loss_events_for_timeline(
    timestamps: list[float],
    expected_interval: float,
    recording_start: float,
) -> list[tuple[float, float, str]]:
    """Detect IQR-based loss events (lightweight version for timelines).

    Returns:
        List of (relative_timestamp, duration, severity).
        severity: "minor" (1-2 frames) / "major" (3+ frames)
    """
    if len(timestamps) < 4 or expected_interval <= 0:
        return []

    intervals = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
    sorted_ivs = sorted(intervals)
    n = len(sorted_ivs)
    q1 = sorted_ivs[n // 4]
    q3 = sorted_ivs[n * 3 // 4]
    iqr = q3 - q1
    loss_threshold = max(q3 + 1.5 * iqr, expected_interval * 1.5)

    events: list[tuple[float, float, str]] = []
    for i, iv in enumerate(intervals):
        if iv > loss_threshold:
            lost = max(0, round(iv / expected_interval) - 1)
            if lost > 0:
                rel_ts = timestamps[i] - recording_start
                severity = "major" if lost >= 3 else "minor"
                events.append((rel_ts, iv, severity))
    return events


# ---------------------------------------------------------------------------
# Lifecycle management (same pattern as QualityAnalyzer)
# ---------------------------------------------------------------------------


class TimelineAnalyzer:
    """API facade for timeline data. Delegates execution to the job queue.

    - Returns cached data immediately when available
    - Otherwise enqueues a job and returns only the status
    - Duplicate execution for the same folder is prevented by JobQueue
    - On failure, surfaces the error from the latest job as-is
    """

    async def get(self, target: Path) -> dict[str, object]:
        """Get timeline data (no side effects)."""
        from app.features.jobs.models import JobStatus
        from app.features.jobs.service import get_job_queue

        cached = load_timeline(target)
        if cached:
            return {"status": "ready", "data": cached.model_dump()}

        queue = get_job_queue()
        active = queue.get_active_timeline_job(target)
        if active is not None:
            if active.status == JobStatus.FAILED:
                return {"status": "error", "error": active.error or "Timeline data generation failed"}
            if active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                return {"status": "analyzing"}

        return {"status": "not_found"}

    async def start(self, target: Path) -> dict[str, object]:
        """Start timeline analysis (idempotent)."""
        from app.features.jobs.models import JobStatus
        from app.features.jobs.service import get_job_queue

        cached = load_timeline(target)
        if cached:
            return {"status": "ready", "data": cached.model_dump()}

        queue = get_job_queue()
        active = queue.get_active_timeline_job(target)
        if active is not None:
            if active.status == JobStatus.FAILED:
                return {"status": "error", "error": active.error or "Timeline data generation failed"}
            if active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                return {"status": "analyzing"}

        if not list(target.glob("*.mcap")):
            return {"status": "not_found", "error": "MCAP file not found"}

        await queue.enqueue_timeline(target)
        return {"status": "analyzing"}
