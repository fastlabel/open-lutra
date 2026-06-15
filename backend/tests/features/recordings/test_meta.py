"""Tests for the recordings/meta module.

Verifies the read/write and partial-update logic for recording_meta.json.
"""

import json
from pathlib import Path
from unittest.mock import patch

from app.features.recordings.meta import (
    RecordingMeta,
    read_recording_meta,
    update_recording_meta,
    write_recording_meta,
)


class TestReadRecordingMeta:
    """Tests for read_recording_meta."""

    def test_file_missing_returns_none(self, tmp_path: Path) -> None:
        """Returns None when the file does not exist (backward compatible with legacy recordings)."""
        assert read_recording_meta(tmp_path) is None

    def test_valid_json(self, tmp_path: Path) -> None:
        """Reads valid JSON and returns a RecordingMeta."""
        (tmp_path / "recording_meta.json").write_text(
            json.dumps({"task_name": "pick", "recording_config_name": "simulator", "tags": ["a", "b"]}),
            encoding="utf-8",
        )
        meta = read_recording_meta(tmp_path)
        assert meta is not None
        assert meta.task_name == "pick"
        assert meta.recording_config_name == "simulator"
        assert meta.tags == ["a", "b"]

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Returns None when JSON parsing fails."""
        (tmp_path / "recording_meta.json").write_text("{ not json", encoding="utf-8")
        assert read_recording_meta(tmp_path) is None

    def test_invalid_schema_returns_none(self, tmp_path: Path) -> None:
        """Returns None when schema validation fails (type mismatch)."""
        (tmp_path / "recording_meta.json").write_text(
            json.dumps({"task_name": 123, "tags": "not-a-list"}),  # Type mismatch
            encoding="utf-8",
        )
        assert read_recording_meta(tmp_path) is None

    def test_oserror_returns_none(self, tmp_path: Path) -> None:
        """Returns None when an OSError occurs during read."""
        (tmp_path / "recording_meta.json").write_text("{}", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            assert read_recording_meta(tmp_path) is None


class TestWriteRecordingMeta:
    """Tests for write_recording_meta."""

    def test_write_creates_file(self, tmp_path: Path) -> None:
        """recording_meta.json is created."""
        meta = RecordingMeta(task_name="task", recording_config_name="myrobot", tags=["t1"])
        write_recording_meta(tmp_path, meta)

        path = tmp_path / "recording_meta.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"task_name": "task", "recording_config_name": "myrobot", "tags": ["t1"]}

    def test_write_overwrites_existing(self, tmp_path: Path) -> None:
        """An existing file is overwritten."""
        write_recording_meta(tmp_path, RecordingMeta(task_name="old"))
        write_recording_meta(tmp_path, RecordingMeta(task_name="new"))

        data = json.loads((tmp_path / "recording_meta.json").read_text(encoding="utf-8"))
        assert data["task_name"] == "new"


class TestUpdateRecordingMeta:
    """Tests for update_recording_meta."""

    def test_creates_meta_when_missing(self, tmp_path: Path) -> None:
        """When no existing file is present, creates a new one from empty meta."""
        result = update_recording_meta(tmp_path, task_name="new", tags=["a"])

        assert result.task_name == "new"
        assert result.recording_config_name is None
        assert result.tags == ["a"]
        # It is also written out as a file
        assert (tmp_path / "recording_meta.json").exists()

    def test_partial_update_preserves_existing_fields(self, tmp_path: Path) -> None:
        """Unspecified fields are preserved."""
        write_recording_meta(
            tmp_path,
            RecordingMeta(task_name="orig", recording_config_name="simulator", tags=["x"]),
        )

        result = update_recording_meta(tmp_path, task_name="updated")

        assert result.task_name == "updated"
        # recording_config_name and tags are preserved
        assert result.recording_config_name == "simulator"
        assert result.tags == ["x"]

    def test_update_only_tags(self, tmp_path: Path) -> None:
        """When updating only tags, task_name is preserved."""
        write_recording_meta(
            tmp_path,
            RecordingMeta(task_name="keep", recording_config_name="simulator", tags=["old"]),
        )

        result = update_recording_meta(tmp_path, tags=["new1", "new2"])

        assert result.task_name == "keep"
        assert result.tags == ["new1", "new2"]

    def test_update_with_no_args_returns_existing(self, tmp_path: Path) -> None:
        """With all args None, returns the existing meta unchanged."""
        write_recording_meta(
            tmp_path,
            RecordingMeta(task_name="orig", tags=["a"]),
        )

        result = update_recording_meta(tmp_path)

        assert result.task_name == "orig"
        assert result.tags == ["a"]

    def test_recording_config_name_not_overwritten(self, tmp_path: Path) -> None:
        """recording_config_name is not changed by update_recording_meta (fixed at recording time)."""
        write_recording_meta(
            tmp_path,
            RecordingMeta(task_name="t", recording_config_name="myrobot", tags=[]),
        )

        result = update_recording_meta(tmp_path, task_name="t2", tags=["x"])

        assert result.recording_config_name == "myrobot"

    def test_empty_string_clears_task_name(self, tmp_path: Path) -> None:
        """Passing an empty string updates task_name to an empty string (only None means \"unspecified\")."""
        write_recording_meta(tmp_path, RecordingMeta(task_name="orig"))

        result = update_recording_meta(tmp_path, task_name="")

        assert result.task_name == ""
