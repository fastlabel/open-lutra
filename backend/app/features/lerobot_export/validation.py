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


def read_recorded_topics(recording_dir: Path) -> dict[str, str]:
    """Return `{topic_name: msg_type}` from a recording's `metadata.yaml`.

    Returns an empty dict when the file is absent or unparseable (the caller
    treats that as "structure unknown", not a mismatch).
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
    topics: dict[str, str] = {}
    for entry in info.get("topics_with_message_count", []):
        topic_metadata = entry.get("topic_metadata", {})
        name = topic_metadata.get("name")
        if name:
            topics[name] = topic_metadata.get("type", "")
    return topics


def find_structure_mismatches(source_dirs: list[Path], config: ExportConfig) -> list[str]:
    """Return one human-readable message per recording missing config topics.

    Recordings without a readable `metadata.yaml` are skipped. An empty result
    means every checkable recording contains all the config's topics.
    """
    required = config.all_topics()
    problems: list[str] = []
    for recording_dir in source_dirs:
        recorded = read_recorded_topics(recording_dir)
        if not recorded:
            logger.warning("Skipping structure check for %s: no readable metadata.yaml", recording_dir.name)
            continue
        missing = [topic for topic in required if topic not in recorded]
        if missing:
            problems.append(f"{recording_dir.name}: missing topic(s) {', '.join(missing)}")
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
