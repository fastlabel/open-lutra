"""Tests for pre-export structure validation against metadata.yaml."""

from pathlib import Path

import pytest

from app.features.lerobot_export.models import ExportConfig, SourceConfig
from app.features.lerobot_export.validation import (
    StructureMismatchError,
    find_structure_mismatches,
    read_recorded_topics,
    validate_recordings,
)


def _config() -> ExportConfig:
    return ExportConfig(
        images={"cam": "/img"},
        observation={"state": [SourceConfig(topic="/state")]},
        action=[SourceConfig(topic="/cmd")],
    )


def _write_metadata(folder: Path, topics: list[str]) -> None:
    entries = "\n".join(
        f"    - topic_metadata:\n        name: {t}\n        type: sensor_msgs/msg/JointState" for t in topics
    )
    folder.joinpath("metadata.yaml").write_text(
        f"rosbag2_bagfile_information:\n  topics_with_message_count:\n{entries}\n", encoding="utf-8"
    )


def test_read_recorded_topics(tmp_path: Path) -> None:
    _write_metadata(tmp_path, ["/img", "/state"])
    topics = read_recorded_topics(tmp_path)
    assert topics == {"/img": "sensor_msgs/msg/JointState", "/state": "sensor_msgs/msg/JointState"}


def test_read_recorded_topics_missing_file(tmp_path: Path) -> None:
    assert read_recorded_topics(tmp_path) == {}


def test_read_recorded_topics_unparseable(tmp_path: Path) -> None:
    tmp_path.joinpath("metadata.yaml").write_text("rosbag2_bagfile_information:\n  topics_with_message_count: [", "utf-8")
    assert read_recorded_topics(tmp_path) == {}


def test_no_mismatch_when_all_topics_present(tmp_path: Path) -> None:
    _write_metadata(tmp_path, ["/img", "/state", "/cmd", "/extra"])
    assert find_structure_mismatches([tmp_path], _config()) == []
    validate_recordings([tmp_path], _config())  # does not raise


def test_mismatch_lists_missing_topics(tmp_path: Path) -> None:
    rec = tmp_path / "rec1"
    rec.mkdir()
    _write_metadata(rec, ["/img"])  # missing /state and /cmd
    problems = find_structure_mismatches([rec], _config())
    assert len(problems) == 1
    assert "/state" in problems[0] and "/cmd" in problems[0]


def test_missing_metadata_is_skipped(tmp_path: Path) -> None:
    # No metadata.yaml -> structure cannot be checked -> not reported as a mismatch.
    assert find_structure_mismatches([tmp_path], _config()) == []


def test_validate_recordings_raises(tmp_path: Path) -> None:
    _write_metadata(tmp_path, ["/img", "/state"])  # missing /cmd
    with pytest.raises(StructureMismatchError, match="/cmd"):
        validate_recordings([tmp_path], _config())
