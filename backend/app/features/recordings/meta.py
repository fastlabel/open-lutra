"""Read and write recording_meta.json.

Stores app-specific metadata (task_name / recording_config_name / tags)
directly inside the recording folder, separately from the metadata.yaml
that ROS2 auto-generates. Returns None on read failure to stay backward-
compatible with older recording folders that do not contain this file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

RECORDING_META_FILENAME = "recording_meta.json"


class RecordingMeta(BaseModel):
    """App-specific metadata for a recording folder."""

    task_name: str | None = None
    recording_config_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


def read_recording_meta(directory: Path) -> RecordingMeta | None:
    """Load recording_meta.json. Returns None if the file is missing or corrupt."""
    meta_path = directory / RECORDING_META_FILENAME
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return RecordingMeta.model_validate(data)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning("Failed to read recording_meta.json (%s): %s", meta_path, e)
        return None


def write_recording_meta(directory: Path, meta: RecordingMeta) -> None:
    """Write recording_meta.json (plain overwrite, not an atomic replace)."""
    meta_path = directory / RECORDING_META_FILENAME
    meta_path.write_text(
        json.dumps(meta.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def update_recording_meta(
    directory: Path,
    *,
    task_name: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, str] | None = None,
) -> RecordingMeta:
    """Partially update recording_meta.json.

    Creates a new file from an empty meta if none exists (older recording
    folders). A None argument means "unspecified = leave unchanged"; an
    empty string, list, or dict explicitly overwrites the field with that
    value. recording_config_name is fixed at recording time and is not
    updated by this function.
    """
    meta = read_recording_meta(directory) or RecordingMeta()
    if task_name is not None:
        meta.task_name = task_name
    if tags is not None:
        meta.tags = list(tags)
    if metadata is not None:
        meta.metadata = dict(metadata)
    write_recording_meta(directory, meta)
    return meta
