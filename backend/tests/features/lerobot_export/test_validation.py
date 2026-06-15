"""Tests for pre-export structure validation against metadata.yaml."""

from pathlib import Path

import pytest

from app.features.lerobot_export.models import ExportConfig, SourceConfig
from app.features.lerobot_export.validation import (
    StructureMismatchError,
    find_structure_mismatches,
    read_recorded_topic_counts,
    validate_recordings,
)


def _config() -> ExportConfig:
    return ExportConfig(
        images={"cam": "/img"},
        observation={"state": [SourceConfig(topic="/state")]},
        action=[SourceConfig(topic="/cmd")],
    )


def _write_metadata(folder: Path, topic_counts: dict[str, int]) -> None:
    # `message_count` is a sibling of `topic_metadata` in each list entry.
    entries = "\n".join(
        f"    - topic_metadata:\n        name: {name}\n        type: sensor_msgs/msg/JointState\n      message_count: {count}"
        for name, count in topic_counts.items()
    )
    folder.joinpath("metadata.yaml").write_text(
        f"rosbag2_bagfile_information:\n  topics_with_message_count:\n{entries}\n", encoding="utf-8"
    )


def test_read_recorded_topic_counts(tmp_path: Path) -> None:
    _write_metadata(tmp_path, {"/img": 10, "/state": 5})
    assert read_recorded_topic_counts(tmp_path) == {"/img": 10, "/state": 5}


def test_read_recorded_topic_counts_missing_file(tmp_path: Path) -> None:
    assert read_recorded_topic_counts(tmp_path) == {}


def test_read_recorded_topic_counts_unparseable(tmp_path: Path) -> None:
    tmp_path.joinpath("metadata.yaml").write_text("rosbag2_bagfile_information:\n  topics_with_message_count: [", "utf-8")
    assert read_recorded_topic_counts(tmp_path) == {}


def test_no_mismatch_when_all_topics_present(tmp_path: Path) -> None:
    _write_metadata(tmp_path, {"/img": 10, "/state": 10, "/cmd": 10, "/extra": 10})
    assert find_structure_mismatches([tmp_path], _config()) == []
    validate_recordings([tmp_path], _config())  # does not raise


def test_mismatch_lists_missing_topics(tmp_path: Path) -> None:
    rec = tmp_path / "rec1"
    rec.mkdir()
    _write_metadata(rec, {"/img": 10})  # missing /state and /cmd
    problems = find_structure_mismatches([rec], _config())
    assert len(problems) == 1
    assert "/state" in problems[0] and "/cmd" in problems[0]


def test_zero_message_topic_is_flagged(tmp_path: Path) -> None:
    # /cmd is present in metadata but recorded 0 messages -> would silently
    # contribute no frames, so it must be flagged like an absent topic.
    _write_metadata(tmp_path, {"/img": 10, "/state": 10, "/cmd": 0})
    problems = find_structure_mismatches([tmp_path], _config())
    assert len(problems) == 1
    assert "/cmd" in problems[0]


def test_missing_metadata_is_rejected(tmp_path: Path) -> None:
    # No metadata.yaml (e.g. still recording) -> rejected, not silently exported.
    problems = find_structure_mismatches([tmp_path], _config())
    assert len(problems) == 1
    assert "metadata.yaml" in problems[0]


def test_validate_recordings_raises(tmp_path: Path) -> None:
    _write_metadata(tmp_path, {"/img": 10, "/state": 10})  # missing /cmd
    with pytest.raises(StructureMismatchError, match="/cmd"):
        validate_recordings([tmp_path], _config())
