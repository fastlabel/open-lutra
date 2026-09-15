"""Reading JointState time-series data.

Decodes Joint-style messages from MCAP and returns a position time series.
Topics that are not images are automatically treated as Joint-style.
The decimation parameter allows down-sampling. Results are cached as JSON.

Performance:
    - The MCAP scan runs **only once**, performing image classification and
      data extraction together
    - Cache file names include the decimation (joint_data_d{decimation}.json)
    - For preview use, decimation around 20 is sufficient (200Hz x 50s = 10,000 -> 500 points)
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, Field

from app.infra.mcap import (
    MCAPReader,
    extract_joint_names,
    extract_joint_positions,
    find_mcap_files,
    is_image_message,
    resolve_timestamp_sec,
)

logger = logging.getLogger(__name__)


def _cache_filename(decimation: int) -> str:
    """Return the cache file name, including the decimation."""
    if decimation <= 1:
        return "joint_data.json"
    return f"joint_data_d{decimation}.json"


class JointData(BaseModel):
    """JointState time-series data."""

    topic: str
    joint_names: list[str]
    timestamps: list[float] = Field(description="Seconds relative to the recording start")
    positions: list[list[float]] = Field(description="Position array at each timestamp")


class JointTopicsResponse(BaseModel):
    """Response for GET /api/files/joints."""

    topics: list[JointData]


def read_joint_data(  # pragma: no cover
    directory: Path,
    topic: str | None = None,
    decimation: int = 1,
) -> JointTopicsResponse:
    """Read Joint-style time-series data from MCAP. Loads from cache if available.

    Args:
        directory: Recording directory.
        topic: Limit to a specific topic if given. None reads all Joint-style topics.
        decimation: Down-sampling rate. 1 = all data, 20 = 1 out of every 20 messages.
    """
    # Check cache (only cached when topic is not specified, keyed by decimation)
    if topic is None:
        cached = _load_cache(directory, decimation)
        if cached is not None:
            return cached

    result = _read_from_mcap(directory, topic, decimation)

    if topic is None:
        _save_cache(directory, result, decimation)

    return result


def _load_cache(directory: Path, decimation: int) -> JointTopicsResponse | None:
    cache_path = directory / _cache_filename(decimation)
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return JointTopicsResponse.model_validate(data)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning("Failed to load joint data cache: %s (%s)", cache_path, e)
        return None


def _save_cache(directory: Path, result: JointTopicsResponse, decimation: int) -> None:
    cache_path = directory / _cache_filename(decimation)
    try:
        cache_path.write_text(
            json.dumps(result.model_dump(), ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Saved joint data cache: %s", cache_path)
    except OSError as e:
        logger.warning("Failed to save joint data cache: %s (%s)", cache_path, e)


def _read_from_mcap(  # pragma: no cover
    directory: Path,
    topic: str | None,
    decimation: int,
) -> JointTopicsResponse:
    """Decode and read Joint-style topic time-series data from MCAP.

    A single MCAP scan performs both image classification and Joint data
    extraction.
    """
    mcap_files = find_mcap_files(directory)
    if not mcap_files:
        raise FileNotFoundError(f"MCAP file not found: {directory}")

    mcap_path = mcap_files[0]

    # Classify each topic by its first message; if it is Joint, also collect
    # subsequent messages.
    image_topics: set[str] = set()
    joint_topics: set[str] = set()
    # Accumulate (timestamp_sec, joint_names, positions) tuples per topic.
    # Holding decoded objects would prevent GC and consume memory, so unpack
    # the names and position array at collection time.
    topic_messages: dict[str, list[tuple[float, list[str], list[float]]]] = defaultdict(list)

    with MCAPReader(mcap_path) as reader:
        for msg in reader.iter_messages():
            t = msg.topic

            if t in image_topics:
                continue

            if t not in joint_topics:
                if is_image_message(msg.decoded):
                    image_topics.add(t)
                    continue
                if topic is not None and t != topic:
                    image_topics.add(t)  # Add to the skip set for convenience
                    continue
                joint_topics.add(t)

            positions = extract_joint_positions(msg.decoded)
            if not positions:
                continue
            ts = resolve_timestamp_sec(msg.decoded, msg.timestamp_ns)
            topic_messages[t].append((ts, extract_joint_names(msg.decoded), positions))

    if not topic_messages:
        return JointTopicsResponse(topics=[])

    all_ts = [ts for msgs in topic_messages.values() for ts, _, _ in msgs]
    recording_start = min(all_ts)

    results: list[JointData] = []
    for topic_name in sorted(topic_messages.keys()):
        msgs = sorted(topic_messages[topic_name], key=lambda m: m[0])

        if decimation > 1:
            msgs = msgs[::decimation]

        if not msgs:
            continue

        # Take joint names from the first message (assumed identical in later messages)
        joint_names = msgs[0][1]
        timestamps = [round(ts - recording_start, 6) for ts, _, _ in msgs]
        positions_series = [positions for _, _, positions in msgs]

        results.append(
            JointData(
                topic=topic_name,
                joint_names=joint_names,
                timestamps=timestamps,
                positions=positions_series,
            )
        )

    return JointTopicsResponse(topics=results)
