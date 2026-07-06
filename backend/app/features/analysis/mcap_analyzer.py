"""MCAP quality analysis engine.

Parses recorded MCAP files and computes per-topic quality metrics. Uses
header.stamp by default to deliver jitter-free accurate metrics, and falls
back to log_time for message types without a header.
"""

import json
import logging
from collections import defaultdict
from pathlib import Path

from app.features.analysis.models import QualityReport
from app.infra.mcap import MCAPReader, find_mcap_files, resolve_timestamp_sec
from app.settings import get_settings
from app.shared.stamp import extract_stamp_sec

logger = logging.getLogger(__name__)


def _analyze_mcap(directory: Path) -> QualityReport:  # pragma: no cover
    """Analyze an MCAP file and produce a quality report.

    Args:
        directory: Recording folder containing metadata.yaml and the mcap file.

    Returns:
        Quality report.

    Raises:
        FileNotFoundError: When no MCAP file is found.
    """
    mcap_files = find_mcap_files(directory)
    if not mcap_files:
        raise FileNotFoundError(f"MCAP file not found: {directory}")

    mcap_path = mcap_files[0]
    file_size = mcap_path.stat().st_size

    topic_timestamps, topic_sizes, topic_types, topic_stamp_sources = _read_mcap(mcap_path)

    return QualityReport.from_mcap_data(
        topic_timestamps=topic_timestamps,
        topic_sizes=topic_sizes,
        topic_types=topic_types,
        file_size=file_size,
        topic_stamp_sources=topic_stamp_sources,
        resolve_expected_hz=get_settings().recording.resolve_expected_hz,
    )


def analyze_and_save(directory: Path) -> QualityReport:  # pragma: no cover
    """Analyze the MCAP and persist the result as quality_report.json."""
    report = _analyze_mcap(directory)
    report_path = directory / "quality_report.json"
    report_path.write_text(
        json.dumps(report.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved quality report: %s", report_path)
    return report


def load_report(directory: Path) -> QualityReport | None:
    """Load the persisted quality_report.json."""
    report_path = directory / "quality_report.json"
    if not report_path.exists():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
        return QualityReport.model_validate(data)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning("Failed to load quality report: %s (%s)", report_path, e)
        return None


def _read_mcap(  # pragma: no cover
    mcap_path: Path,
) -> tuple[dict[str, list[float]], dict[str, list[int]], dict[str, str], dict[str, str]]:
    """Extract timestamps, sizes, and type information from an MCAP file.

    Prefers header.stamp and falls back to log_time for message types
    without it. The stamp source is determined from each topic's first
    message and reused for the rest of the topic.

    Returns:
        (topic_timestamps, topic_sizes, topic_types, topic_stamp_sources)
        topic_stamp_sources: dict of topic name -> "header_stamp" | "log_time"
    """
    topic_timestamps: dict[str, list[float]] = defaultdict(list)
    topic_sizes: dict[str, list[int]] = defaultdict(list)
    topic_types: dict[str, str] = {}
    topic_stamp_sources: dict[str, str] = {}

    with MCAPReader(mcap_path) as reader:
        for msg in reader.iter_messages():
            topic = msg.topic

            # Record the topic type
            if topic not in topic_types:
                topic_types[topic] = msg.msg_type

            # Decide the stamp source (only once per topic, on the first message)
            if topic not in topic_stamp_sources:
                stamp = extract_stamp_sec(msg.decoded)
                topic_stamp_sources[topic] = "header_stamp" if stamp is not None and stamp > 0 else "log_time"

            # Get the timestamp (prefer header.stamp, fall back to log_time based on the decision above)
            if topic_stamp_sources[topic] == "header_stamp":
                ts_sec = resolve_timestamp_sec(msg.decoded, msg.timestamp_ns)
            else:
                ts_sec = msg.timestamp_ns / 1e9

            topic_timestamps[topic].append(ts_sec)
            topic_sizes[topic].append(msg.size_bytes)

    return dict(topic_timestamps), dict(topic_sizes), topic_types, topic_stamp_sources
