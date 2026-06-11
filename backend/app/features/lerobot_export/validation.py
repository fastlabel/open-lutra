"""Pre-export structure validation.

Compares each recording's `metadata.yaml` (the ros2 bag manifest) against the
export config and fails fast when a recording does not contain every topic the
config references — otherwise that recording would silently produce an empty or
malformed episode. A recording without a readable `metadata.yaml` is skipped
(its structure cannot be verified from the manifest).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from app.features.lerobot_export.models import ExportConfig

logger = logging.getLogger(__name__)


class StructureMismatchError(ValueError):
    """Raised when a recording's topic structure does not match the export config."""


def read_recorded_topic_counts(recording_dir: Path) -> dict[str, int]:
    """Return `{topic_name: message_count}` from a recording's `metadata.yaml`.

    Returns an empty dict when the file is absent or unparseable (the caller
    treats that as "structure unknown", not a mismatch). `message_count` is a
    sibling of `topic_metadata` within each `topics_with_message_count` entry.
    """
    meta_path = recording_dir / "metadata.yaml"
    if not meta_path.exists():
        return {}
    try:
        data = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        logger.debug("Failed to read metadata.yaml (%s): %s", meta_path, e)
        return {}

    info = (data or {}).get("rosbag2_bagfile_information", {})
    counts: dict[str, int] = {}
    for entry in info.get("topics_with_message_count", []):
        name = entry.get("topic_metadata", {}).get("name")
        if name:
            counts[name] = entry.get("message_count", 0)
    return counts


def find_structure_mismatches(source_dirs: list[Path], config: ExportConfig) -> list[str]:
    """Return one message per recording whose config topics are missing or empty.

    A config topic that is absent from `metadata.yaml`, or present with
    `message_count == 0`, would silently contribute zero frames, so both are
    reported. Recordings without a readable `metadata.yaml` are skipped (their
    structure cannot be verified from the manifest).
    """
    required = config.all_topics()
    problems: list[str] = []
    for recording_dir in source_dirs:
        counts = read_recorded_topic_counts(recording_dir)
        if not counts:
            logger.warning("Skipping structure check for %s: no readable metadata.yaml", recording_dir.name)
            continue
        bad = [topic for topic in required if counts.get(topic, 0) == 0]
        if bad:
            problems.append(f"{recording_dir.name}: missing or empty topic(s) {', '.join(bad)}")
    return problems


def validate_recordings(source_dirs: list[Path], config: ExportConfig) -> None:
    """Raise if any recording's structure does not match the export config.

    Raises:
        StructureMismatchError: With per-recording detail of the missing topics.
    """
    problems = find_structure_mismatches(source_dirs, config)
    if problems:
        raise StructureMismatchError(
            "Recording structure does not match the export config:\n" + "\n".join(f"- {p}" for p in problems)
        )
