"""Tests for the recordings/meta module.

Verifies the read/write and partial-update logic for recording_meta.json.
"""

import json
from pathlib import Path
from unittest.mock import patch

from app.features.recordings.meta import (
    RecordingMeta,
    merge_recording_meta,
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
            json.dumps(
                {
                    "task_name": "pick",
                    "recording_config_name": "simulator",
                    "tags": ["a", "b"],
                    "metadata": {"operator_id": "op001", "target_object": "box"},
                }
            ),
            encoding="utf-8",
        )
        meta = read_recording_meta(tmp_path)
        assert meta is not None
        assert meta.task_name == "pick"
        assert meta.recording_config_name == "simulator"
        assert meta.tags == ["a", "b"]
        assert meta.metadata == {"operator_id": "op001", "target_object": "box"}

    def test_missing_metadata_defaults_to_empty(self, tmp_path: Path) -> None:
        """Legacy files without a metadata key default to an empty dict."""
        (tmp_path / "recording_meta.json").write_text(
            json.dumps({"task_name": "pick", "tags": []}),
            encoding="utf-8",
        )
        meta = read_recording_meta(tmp_path)
        assert meta is not None
        assert meta.metadata == {}

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Returns None when JSON parsing fails."""
        (tmp_path / "recording_meta.json").write_text("{ not json", encoding="utf-8")
        assert read_recording_meta(tmp_path) is None

    def test_invalid_schema_returns_none(self, tmp_path: Path) -> None:
        """Returns None when schema validation fails (type mismatch)."""
        (tmp_path / "recording_meta.json").write_text(
            json.dumps({"task_name": 123, "tags": "not-a-list"}),
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
        meta = RecordingMeta(
            task_name="task",
            recording_config_name="myrobot",
            tags=["t1"],
            metadata={"operator_id": "op001"},
        )
        write_recording_meta(tmp_path, meta)

        path = tmp_path / "recording_meta.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {
            "task_name": "task",
            "recording_config_name": "myrobot",
            "tags": ["t1"],
            "metadata": {"operator_id": "op001"},
        }

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
        assert (tmp_path / "recording_meta.json").exists()

    def test_partial_update_preserves_existing_fields(self, tmp_path: Path) -> None:
        """Unspecified fields are preserved."""
        write_recording_meta(
            tmp_path,
            RecordingMeta(task_name="orig", recording_config_name="simulator", tags=["x"]),
        )

        result = update_recording_meta(tmp_path, task_name="updated")

        assert result.task_name == "updated"
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

    def test_update_only_metadata(self, tmp_path: Path) -> None:
        """When updating only metadata, task_name and tags are preserved."""
        write_recording_meta(
            tmp_path,
            RecordingMeta(task_name="keep", tags=["x"], metadata={"operator_id": "old"}),
        )

        result = update_recording_meta(tmp_path, metadata={"operator_id": "op002", "target_object": "cup"})

        assert result.task_name == "keep"
        assert result.tags == ["x"]
        assert result.metadata == {"operator_id": "op002", "target_object": "cup"}

    def test_metadata_preserved_when_unspecified(self, tmp_path: Path) -> None:
        """Existing metadata is preserved when only task_name is updated."""
        write_recording_meta(
            tmp_path,
            RecordingMeta(task_name="orig", metadata={"operator_id": "op001"}),
        )

        result = update_recording_meta(tmp_path, task_name="updated")

        assert result.metadata == {"operator_id": "op001"}

    def test_empty_dict_clears_metadata(self, tmp_path: Path) -> None:
        """Passing an empty dict clears metadata (only None means \"unspecified\")."""
        write_recording_meta(tmp_path, RecordingMeta(metadata={"operator_id": "op001"}))

        result = update_recording_meta(tmp_path, metadata={})

        assert result.metadata == {}


class TestMergeRecordingMeta:
    """Tests for merge_recording_meta."""

    def test_sets_given_keys_and_keeps_other_fields(self, tmp_path: Path) -> None:
        """Given keys are overwritten or added; other keys, task_name, and tags are preserved."""
        write_recording_meta(
            tmp_path,
            RecordingMeta(
                task_name="keep",
                recording_config_name="sim",
                tags=["x"],
                metadata={"operator_id": "op001", "target_object": "box"},
            ),
        )

        result = merge_recording_meta(
            tmp_path, metadata={"target_object": "cup", "scene": "kitchen"}, add_tags=[], remove_tags=[]
        )

        assert result.metadata == {"operator_id": "op001", "target_object": "cup", "scene": "kitchen"}
        assert result.task_name == "keep"
        assert result.recording_config_name == "sim"
        assert result.tags == ["x"]
        assert read_recording_meta(tmp_path) == result

    def test_creates_meta_when_missing(self, tmp_path: Path) -> None:
        """Older recording folders without recording_meta.json get a new file."""
        result = merge_recording_meta(tmp_path, metadata={"target_object": "cup"}, add_tags=["a"], remove_tags=[])

        assert result.metadata == {"target_object": "cup"}
        assert result.tags == ["a"]
        assert read_recording_meta(tmp_path) == result

    def test_add_tags_appends_in_order_without_duplicates(self, tmp_path: Path) -> None:
        """New tags go to the end in the given order; tags already present (or repeated) are not duplicated."""
        write_recording_meta(tmp_path, RecordingMeta(tags=["good", "retry"]))

        result = merge_recording_meta(
            tmp_path, metadata={}, add_tags=["reviewed", "good", "night", "reviewed"], remove_tags=[]
        )

        assert result.tags == ["good", "retry", "reviewed", "night"]

    def test_remove_tags_drops_only_present_ones(self, tmp_path: Path) -> None:
        """Listed tags are removed where present; absent ones are ignored and the rest keep their order."""
        write_recording_meta(tmp_path, RecordingMeta(tags=["good", "retry", "blurry"]))

        result = merge_recording_meta(tmp_path, metadata={}, add_tags=[], remove_tags=["retry", "missing"])

        assert result.tags == ["good", "blurry"]

    def test_metadata_and_tags_in_one_write(self, tmp_path: Path) -> None:
        """Metadata and both tag lists are applied together with a single file write."""
        write_recording_meta(tmp_path, RecordingMeta(tags=["retry"], metadata={"operator_id": "op001"}))

        with patch("app.features.recordings.meta.write_recording_meta", wraps=write_recording_meta) as mock_write:
            result = merge_recording_meta(
                tmp_path, metadata={"target_object": "cup"}, add_tags=["reviewed"], remove_tags=["retry"]
            )

        assert mock_write.call_count == 1
        assert result.metadata == {"operator_id": "op001", "target_object": "cup"}
        assert result.tags == ["reviewed"]
        assert read_recording_meta(tmp_path) == result
