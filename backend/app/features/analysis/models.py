"""Domain models for quality analysis.

Holds the logic for computing per-topic quality metrics and overall reports
from MCAP files. Kept separate from the API response Pydantic schemas
(schemas.py).

See docs/domain/quality_analysis.md for details on quality metrics.
"""

import statistics
from collections.abc import Callable

from pydantic import BaseModel, Field

# --- Quality status thresholds ---
_LOSS_RATE_WARN = 0.02  # warning when >= 2%
_LOSS_RATE_DANGER = 0.05  # danger when >= 5%
_CONTINUITY_WARN = 0.98  # warning when < 0.98
_CONTINUITY_DANGER = 0.9  # danger when < 0.9
_GAP_MULTIPLIER = 3.0  # mark as a gap when interval exceeds 3x the expected interval

# Standard values used for automatic frequency estimation
_STANDARD_FREQUENCIES = [10, 15, 20, 25, 30, 50, 60, 100, 120, 200, 500]


class GapInfo(BaseModel):
    """Timestamp gap information (legacy, fixed-multiplier based)."""

    timestamp_sec: float = Field(..., description="Seconds elapsed since recording start")
    duration_sec: float = Field(..., description="Gap length in seconds")


class LossEvent(BaseModel):
    """Message loss event (IQR statistical threshold + rounded estimate).

    When used with header.stamp timestamps, jitter is removed so loss
    detection is highly accurate.
    """

    timestamp_sec: float = Field(..., description="Seconds elapsed since recording start")
    duration_sec: float = Field(..., description="Length of the empty interval in seconds")
    lost_count: int = Field(..., description="Estimated number of lost messages")
    severity: str = Field(..., description="minor(1-2) / major(3+)")


class MessageSizeStats(BaseModel):
    """Message size statistics."""

    min_bytes: int
    max_bytes: int
    avg_bytes: int
    std_bytes: float
    zero_size_count: int = Field(..., description="Number of zero-byte messages (possibly malformed frames)")

    @classmethod
    def empty(cls) -> "MessageSizeStats":
        """Return zeroed statistics when there are no messages."""
        return cls(min_bytes=0, max_bytes=0, avg_bytes=0, std_bytes=0.0, zero_size_count=0)

    @classmethod
    def from_sizes(cls, sizes: list[int]) -> "MessageSizeStats":
        """Compute statistics from a list of message sizes."""
        if not sizes:
            return cls.empty()
        zero_count = sizes.count(0)
        avg = int(statistics.mean(sizes))
        std = statistics.stdev(sizes) if len(sizes) > 1 else 0.0
        return cls(
            min_bytes=min(sizes),
            max_bytes=max(sizes),
            avg_bytes=avg,
            std_bytes=round(std, 1),
            zero_size_count=zero_count,
        )


class TopicQuality(BaseModel):
    """Per-topic quality metrics."""

    name: str
    msg_type: str
    message_count: int
    actual_frequency_hz: float
    expected_frequency_hz: float
    loss_rate: float
    frequency_std_hz: float
    data_continuity_score: float
    gap_count: int
    gaps: list[GapInfo]
    loss_events: list[LossEvent] = Field(..., description="Accurate loss events based on IQR")
    loss_count: int = Field(..., description="Total estimated lost messages across all loss events")
    minor_loss_count: int = Field(..., description="Number of minor (1-2 frame) loss events")
    major_loss_count: int = Field(..., description="Number of major (3+ frame) loss events")
    timestamp_source: str = Field(..., description="Timestamp source (header_stamp/log_time)")
    avg_message_size_bytes: int
    size_stats: MessageSizeStats
    start_delay_sec: float = Field(
        ..., description="Delay from recording start to this topic's first message (seconds)"
    )
    end_early_sec: float = Field(
        ..., description="Empty interval from this topic's last message to recording end (seconds)"
    )
    status: str

    @classmethod
    def from_timestamps(
        cls,
        *,
        name: str,
        msg_type: str,
        timestamps: list[float],
        sizes: list[int],
        recording_start: float,
        duration_sec: float,
        timestamp_source: str = "log_time",
        config_expected_hz: float | None = None,
    ) -> "TopicQuality":
        """Compute quality metrics from timestamps and sizes.

        When ``config_expected_hz`` is provided (the RECORDING_CONFIG
        ``expected_hz_patterns`` value for this topic), it is used as the
        expected frequency instead of the rate estimated from the data. It
        drives the loss-rate denominator, the gap/loss detection thresholds,
        and the reported ``expected_frequency_hz``. A ``None`` or non-positive
        value falls back to snapping the measured rate to a standard frequency.
        """
        timestamps.sort()
        msg_count = len(timestamps)
        size_stats = MessageSizeStats.from_sizes(sizes)
        avg_size = int(statistics.mean(sizes)) if sizes else 0

        start_delay = timestamps[0] - recording_start if timestamps else 0.0
        recording_end = recording_start + duration_sec
        end_early = recording_end - timestamps[-1] if timestamps else 0.0

        # Skip interval-based analysis when there are too few messages. Interval
        # metrics need >= 2 samples, but with a config-declared expected Hz the
        # loss rate can still be computed from the count against the configured
        # rate, so a near-empty configured topic is not reported as healthy.
        if msg_count < 2:
            expected_hz = config_expected_hz if config_expected_hz is not None and config_expected_hz > 0 else 0.0
            loss_rate = cls._count_loss_rate(msg_count, expected_hz, duration_sec)
            return cls(
                name=name,
                msg_type=msg_type,
                message_count=msg_count,
                actual_frequency_hz=0.0,
                expected_frequency_hz=expected_hz,
                loss_rate=round(loss_rate, 4),
                frequency_std_hz=0.0,
                data_continuity_score=1.0,
                gap_count=0,
                gaps=[],
                loss_events=[],
                loss_count=0,
                minor_loss_count=0,
                major_loss_count=0,
                timestamp_source=timestamp_source,
                avg_message_size_bytes=avg_size,
                size_stats=size_stats,
                start_delay_sec=round(start_delay, 3),
                end_early_sec=round(max(0.0, end_early), 3),
                status=cls._status_from_loss_rate(loss_rate),
            )

        # Frequency calculation (median of message intervals)
        intervals = [timestamps[i + 1] - timestamps[i] for i in range(msg_count - 1)]
        median_interval = statistics.median(intervals)
        actual_hz = 1.0 / median_interval if median_interval > 0 else 0.0
        # A config-declared expected Hz wins; otherwise snap the measured rate to
        # the nearest standard frequency.
        expected_hz = (
            config_expected_hz
            if config_expected_hz is not None and config_expected_hz > 0
            else cls._estimate_expected_frequency(actual_hz)
        )

        # Frequency standard deviation
        freq_values = [1.0 / iv if iv > 0 else 0.0 for iv in intervals]
        freq_std = statistics.stdev(freq_values) if len(freq_values) > 1 else 0.0

        # Loss rate (message count against the expected frame count)
        loss_rate = cls._count_loss_rate(msg_count, expected_hz, duration_sec)

        expected_interval = 1.0 / expected_hz if expected_hz > 0 else median_interval

        # Legacy gap detection (intervals exceeding 3x the expected interval; kept for backward compatibility)
        gap_threshold = expected_interval * _GAP_MULTIPLIER
        gaps: list[GapInfo] = []
        for iv_idx, iv in enumerate(intervals):
            if iv > gap_threshold:
                gap_ts = timestamps[iv_idx] - recording_start
                gaps.append(GapInfo(timestamp_sec=round(gap_ts, 2), duration_sec=round(iv, 2)))

        # IQR-based loss event detection (especially accurate with header.stamp)
        loss_events = cls._detect_loss_events(intervals, timestamps, expected_interval, recording_start)

        # Add empty intervals at the start/end of the recording as loss events
        # (gap between recording_start and the first message, and between the last message and recording_end)
        edge_events = cls._detect_edge_loss(
            start_delay=start_delay,
            end_early=end_early,
            expected_interval=expected_interval,
            last_ts_rel=timestamps[-1] - recording_start,
        )
        # Sort by ascending timestamp_sec (start_delay -> middle gaps -> end_early).
        # Without sorting, edge events would cluster at the front and break the chronological order in the UI.
        loss_events = sorted(edge_events + loss_events, key=lambda le: le.timestamp_sec)

        loss_count = sum(le.lost_count for le in loss_events)
        minor_loss_count = sum(1 for le in loss_events if le.severity == "minor")
        major_loss_count = sum(1 for le in loss_events if le.severity == "major")

        # Continuity score (computed from loss_events, more accurate than legacy gaps)
        loss_total_sec = (
            sum(le.duration_sec for le in loss_events) if loss_events else sum(g.duration_sec for g in gaps)
        )
        topic_duration = timestamps[-1] - timestamps[0]
        continuity = max(0.0, 1.0 - (loss_total_sec / topic_duration)) if topic_duration > 0 else 1.0

        return cls(
            name=name,
            msg_type=msg_type,
            message_count=msg_count,
            actual_frequency_hz=round(actual_hz, 1),
            expected_frequency_hz=expected_hz,
            loss_rate=round(loss_rate, 4),
            frequency_std_hz=round(freq_std, 2),
            data_continuity_score=round(continuity, 3),
            gap_count=len(gaps),
            gaps=gaps,
            loss_events=loss_events,
            loss_count=loss_count,
            minor_loss_count=minor_loss_count,
            major_loss_count=major_loss_count,
            timestamp_source=timestamp_source,
            avg_message_size_bytes=avg_size,
            size_stats=size_stats,
            start_delay_sec=round(start_delay, 3),
            end_early_sec=round(max(0.0, end_early), 3),
            status=cls._determine_status(major_loss_count, minor_loss_count, msg_count, loss_count),
        )

    @staticmethod
    def _detect_edge_loss(
        *,
        start_delay: float,
        end_early: float,
        expected_interval: float,
        last_ts_rel: float,
    ) -> list[LossEvent]:
        """Detect empty intervals at the recording start/end as loss events.

        IQR detection only looks at intervals between adjacent messages, so
        the gap from recording_start to the first message (start_delay) and
        from the last message to recording_end (end_early) must be detected
        separately.
        """
        if expected_interval <= 0:
            return []

        events: list[LossEvent] = []
        threshold = expected_interval * 1.5

        # Loss at the start: from recording start to the first message
        if start_delay > threshold:
            lost = max(0, round(start_delay / expected_interval) - 1)
            if lost > 0:
                events.append(
                    LossEvent(
                        timestamp_sec=0.0,
                        duration_sec=round(start_delay, 4),
                        lost_count=lost,
                        severity="major" if lost >= 3 else "minor",
                    )
                )

        # Loss at the end: from the last message to recording end
        if end_early > threshold:
            lost = max(0, round(end_early / expected_interval) - 1)
            if lost > 0:
                events.append(
                    LossEvent(
                        timestamp_sec=round(last_ts_rel, 3),
                        duration_sec=round(end_early, 4),
                        lost_count=lost,
                        severity="major" if lost >= 3 else "minor",
                    )
                )

        return events

    @staticmethod
    def _detect_loss_events(
        intervals: list[float],
        timestamps: list[float],
        expected_interval: float,
        recording_start: float,
    ) -> list[LossEvent]:
        """Detect abnormal intervals using an IQR statistical threshold and estimate lost messages.

        With header.stamp timestamps, jitter is extremely small, so the IQR
        threshold becomes tight enough to accurately detect even single
        lost frames.
        """
        if len(intervals) < 4 or expected_interval <= 0:
            return []

        sorted_ivs = sorted(intervals)
        n = len(sorted_ivs)
        q1 = sorted_ivs[n // 4]
        q3 = sorted_ivs[n * 3 // 4]
        iqr = q3 - q1
        # IQR threshold: Q3 + 1.5*IQR. Guarantee at least 1.5x the expected interval.
        loss_threshold = max(q3 + 1.5 * iqr, expected_interval * 1.5)

        events: list[LossEvent] = []
        for iv_idx, iv in enumerate(intervals):
            if iv > loss_threshold:
                lost = max(0, round(iv / expected_interval) - 1)
                if lost > 0:
                    events.append(
                        LossEvent(
                            timestamp_sec=round(timestamps[iv_idx] - recording_start, 3),
                            duration_sec=round(iv, 4),
                            lost_count=lost,
                            severity="major" if lost >= 3 else "minor",
                        )
                    )
        return events

    @staticmethod
    def _estimate_expected_frequency(actual_hz: float) -> float:
        """Estimate the nearest standard frequency from the measured frequency."""
        if actual_hz <= 0:
            return 0.0
        return float(min(_STANDARD_FREQUENCIES, key=lambda f: abs(f - actual_hz)))

    @staticmethod
    def _count_loss_rate(msg_count: int, expected_hz: float, duration_sec: float) -> float:
        """Count-based loss rate: 1 - actual/expected.

        Returns 0.0 when the expected frame count is unknown (expected_hz or
        duration is non-positive).
        """
        if expected_hz > 0 and duration_sec > 0:
            expected_count = expected_hz * duration_sec
            return max(0.0, 1.0 - (msg_count / expected_count))
        return 0.0

    @staticmethod
    def _status_from_loss_rate(loss_rate: float) -> str:
        """Map a count-based loss rate to a quality status.

        Used when there are too few messages for interval-based severity
        classification but a configured expected Hz still yields a loss rate.
        """
        if loss_rate > _LOSS_RATE_DANGER:
            return "danger"
        if loss_rate > _LOSS_RATE_WARN:
            return "warning"
        return "ok"

    @staticmethod
    def _determine_status(major_loss: int, minor_loss: int, msg_count: int, loss_count: int = 0) -> str:
        """Determine the quality status.

        Returns "danger" if any major_loss (3+ frame drops) exists, "warning"
        if any minor_loss (1-2 frames) exists. Also returns "danger" when
        loss_rate exceeds 5% (to reflect large edge losses, etc.).
        """
        if msg_count == 0:
            return "ok"
        total_expected = msg_count + loss_count
        loss_rate = loss_count / total_expected if total_expected > 0 else 0.0
        if loss_rate > 0.05 or major_loss > 0:
            return "danger"
        if loss_rate > 0.02 or minor_loss > 0:
            return "warning"
        return "ok"


class QualityReport(BaseModel):
    """Overall quality report."""

    duration_sec: float
    total_messages: int
    total_topics: int
    file_size_bytes: int
    topics: list[TopicQuality]

    @classmethod
    def from_mcap_data(
        cls,
        *,
        topic_timestamps: dict[str, list[float]],
        topic_sizes: dict[str, list[int]],
        topic_types: dict[str, str],
        file_size: int,
        topic_stamp_sources: dict[str, str] | None = None,
        resolve_expected_hz: Callable[[str], float | None] | None = None,
    ) -> "QualityReport":
        """Build a quality report from data extracted from MCAP.

        ``resolve_expected_hz`` resolves the config-declared expected Hz
        (RECORDING_CONFIG ``expected_hz_patterns``) for a topic name; when it
        returns a value, that value overrides the auto-estimated expected Hz
        for that topic (see ``TopicQuality.from_timestamps``).
        """
        stamp_sources = topic_stamp_sources or {}

        # Overall timestamp range
        all_timestamps: list[float] = []
        total_messages = 0
        for timestamps in topic_timestamps.values():
            all_timestamps.extend(timestamps)
            total_messages += len(timestamps)

        duration_sec = (max(all_timestamps) - min(all_timestamps)) if all_timestamps else 0.0
        recording_start = min(all_timestamps) if all_timestamps else 0.0

        # Per-topic quality analysis
        topic_qualities = [
            TopicQuality.from_timestamps(
                name=topic_name,
                msg_type=topic_types.get(topic_name, "unknown"),
                timestamps=timestamps,
                sizes=topic_sizes[topic_name],
                recording_start=recording_start,
                duration_sec=duration_sec,
                timestamp_source=stamp_sources.get(topic_name, "log_time"),
                config_expected_hz=(resolve_expected_hz(topic_name) if resolve_expected_hz else None),
            )
            for topic_name, timestamps in sorted(topic_timestamps.items())
        ]

        return cls(
            duration_sec=round(duration_sec, 2),
            total_messages=total_messages,
            total_topics=len(topic_qualities),
            file_size_bytes=file_size,
            topics=topic_qualities,
        )
