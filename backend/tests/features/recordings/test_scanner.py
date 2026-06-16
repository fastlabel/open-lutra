"""Tests for the recordings/scanner module.

Verifies the pure filesystem logic of scan_output_dir / read_metadata_summary.
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

from app.features.recordings.scanner import (
    collect_recent_task_names,
    read_metadata_summary,
    scan_output_dir,
)

# ---------------------------------------------------------------------------
# read_metadata_summary
# ---------------------------------------------------------------------------

METADATA_YAML = """\
rosbag2_bagfile_information:
  version: 8
  storage_identifier: mcap
  duration:
    nanoseconds: 5000000000
  starting_time:
    nanoseconds_since_epoch: 1700000000000000000
  message_count: 300
  topics_with_message_count:
    - topic_metadata:
        name: /joint_states
        type: sensor_msgs/msg/JointState
      message_count: 200
    - topic_metadata:
        name: /tf
        type: tf2_msgs/msg/TFMessage
      message_count: 100
  files:
    - path: recording_0.mcap
      starting_time:
        nanoseconds_since_epoch: 9999999999
      duration:
        nanoseconds: 1111111111
"""


def _make_recording(folder: Path, *, metadata: str | None = None, files: dict[str, bytes] | None = None) -> Path:
    """Helper that creates a recording folder containing a .mcap."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "recording_0.mcap").write_bytes(b"x")
    if metadata is not None:
        (folder / "metadata.yaml").write_text(metadata, encoding="utf-8")
    for name, content in (files or {}).items():
        (folder / name).write_bytes(content)
    return folder


class TestReadMetadataSummary:
    """Tests for read_metadata_summary."""

    def test_full_metadata(self, tmp_path: Path) -> None:
        """Parses topic count, start time, duration, and total message count correctly."""
        (tmp_path / "metadata.yaml").write_text(METADATA_YAML, encoding="utf-8")

        topic_count, start_ns, dur_ns, msg_count = read_metadata_summary(tmp_path)

        assert topic_count == 2
        assert start_ns == 1700000000000000000
        assert dur_ns == 5000000000
        assert msg_count == 300

    def test_no_metadata_file(self, tmp_path: Path) -> None:
        """Returns all None when metadata.yaml is absent."""
        assert read_metadata_summary(tmp_path) == (None, None, None, None)

    def test_unreadable_file(self, tmp_path: Path) -> None:
        """Returns all None when the file is unreadable."""
        meta = tmp_path / "metadata.yaml"
        meta.write_text("dummy", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            assert read_metadata_summary(tmp_path) == (None, None, None, None)

    def test_empty_metadata(self, tmp_path: Path) -> None:
        """An empty metadata.yaml returns all None."""
        (tmp_path / "metadata.yaml").write_text("", encoding="utf-8")

        assert read_metadata_summary(tmp_path) == (None, None, None, None)

    def test_no_topics(self, tmp_path: Path) -> None:
        """topic_count and message_count are None when no topic entries are present."""
        yaml_content = """\
rosbag2_bagfile_information:
  duration:
    nanoseconds: 1000
  starting_time:
    nanoseconds_since_epoch: 2000
"""
        (tmp_path / "metadata.yaml").write_text(yaml_content, encoding="utf-8")

        topic_count, start_ns, dur_ns, msg_count = read_metadata_summary(tmp_path)

        assert topic_count is None
        assert start_ns == 2000
        assert dur_ns == 1000
        assert msg_count is None

    def test_files_section_values_ignored(self, tmp_path: Path) -> None:
        """starting_time/duration inside the files: section are distinguished from the top level."""
        (tmp_path / "metadata.yaml").write_text(METADATA_YAML, encoding="utf-8")

        _, start_ns, dur_ns, _ = read_metadata_summary(tmp_path)

        # Picks the top-level values, not 9999999999 / 1111111111 under files
        assert start_ns == 1700000000000000000
        assert dur_ns == 5000000000

    def test_message_count_top_level_only(self, tmp_path: Path) -> None:
        """Returns the top-level message_count, not the values nested under topics_with_message_count."""
        (tmp_path / "metadata.yaml").write_text(METADATA_YAML, encoding="utf-8")

        _, _, _, msg_count = read_metadata_summary(tmp_path)

        # Uses the top-level 300, not the nested 200/100
        assert msg_count == 300


# ---------------------------------------------------------------------------
# scan_output_dir
# ---------------------------------------------------------------------------


class TestScanOutputDir:
    """Tests for scan_output_dir."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        """An empty directory returns an empty list."""
        assert scan_output_dir(tmp_path) == []

    def test_top_level_files_ignored(self, tmp_path: Path) -> None:
        """Files directly under output_dir are ignored (non-recording artifacts are not returned)."""
        (tmp_path / "stray.mcap").write_bytes(b"x")
        (tmp_path / "README.md").write_bytes(b"y")

        assert scan_output_dir(tmp_path) == []

    def test_folder_without_mcap_filtered(self, tmp_path: Path) -> None:
        """Subdirectories without a .mcap are not returned (not treated as recording folders)."""
        (tmp_path / "random_folder").mkdir()
        (tmp_path / "random_folder" / "note.txt").write_bytes(b"x")

        assert scan_output_dir(tmp_path) == []

    def test_single_recording_folder(self, tmp_path: Path) -> None:
        """A subdirectory containing a .mcap is returned as a recording folder."""
        _make_recording(tmp_path / "recording_001")

        entries = scan_output_dir(tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "recording_001"
        assert entries[0].path == "recording_001"
        assert entries[0].size > 0
        assert entries[0].modified_at > 0

    def test_flags_detection(self, tmp_path: Path) -> None:
        """Detects flags from generated-artifact files inside the recording folder."""
        rec = _make_recording(
            tmp_path / "rec",
            files={"quality_report.json": b"q"},
        )
        del rec  # Path is the return value of _make_recording

        entries = scan_output_dir(tmp_path)

        assert entries[0].has_quality_report is True

    def test_flags_absent(self, tmp_path: Path) -> None:
        """All flags are False when no generated artifacts are present."""
        _make_recording(tmp_path / "rec")

        entries = scan_output_dir(tmp_path)

        assert entries[0].has_quality_report is False
        assert entries[0].validation_overall_status is None
        assert entries[0].upload_status is None

    def test_validation_overall_status_loaded(self, tmp_path: Path) -> None:
        """When validation_result.json exists, its overall_status is reflected in FileEntry."""
        report = {
            "overall_status": "warn",
            "results": [],
            "task_name": "pick",
            "executed_at": "2026-05-25T00:00:00",
        }
        _make_recording(
            tmp_path / "rec",
            files={"validation_result.json": json.dumps(report).encode("utf-8")},
        )

        entries = scan_output_dir(tmp_path)

        assert entries[0].validation_overall_status == "warn"

    def test_upload_status_loaded(self, tmp_path: Path) -> None:
        """When upload_state.json exists, its status is reflected in FileEntry."""
        state = {
            "status": "uploaded",
            "destination": "lutra-test",
            "key": "uploads/rec.zip",
            "etag": '"abc"',
            "size_bytes": 1024,
            "bytes_transferred": 1024,
            "uploaded_at": "2026-05-25T12:00:00+00:00",
            "error": None,
        }
        _make_recording(
            tmp_path / "rec",
            files={"upload_state.json": json.dumps(state).encode("utf-8")},
        )

        entries = scan_output_dir(tmp_path)

        assert entries[0].upload_status == "uploaded"

    def test_metadata_summary_included(self, tmp_path: Path) -> None:
        """When metadata.yaml is present, topic_count/recording_start_ns/duration_ns/message_count are filled in."""
        _make_recording(tmp_path / "rec", metadata=METADATA_YAML)

        entries = scan_output_dir(tmp_path)

        assert entries[0].topic_count == 2
        assert entries[0].recording_start_ns == 1700000000000000000
        assert entries[0].duration_ns == 5000000000
        assert entries[0].message_count == 300

    def test_size_is_folder_total(self, tmp_path: Path) -> None:
        """size is the total byte count of all files in the folder."""
        rec = tmp_path / "rec"
        rec.mkdir()
        (rec / "recording_0.mcap").write_bytes(b"x" * 100)
        (rec / "telemetry.json").write_bytes(b"y" * 50)

        entries = scan_output_dir(tmp_path)

        assert entries[0].size == 150

    def test_ds_store_excluded(self, tmp_path: Path) -> None:
        """.DS_Store is excluded at the top level."""
        (tmp_path / ".DS_Store").write_bytes(b"\x00")
        _make_recording(tmp_path / "rec")

        entries = scan_output_dir(tmp_path)

        assert len(entries) == 1
        assert entries[0].name == "rec"

    def test_lerobot_exports_dir_excluded(self, tmp_path: Path) -> None:
        """The reserved _lerobot_exports directory is never listed as a recording."""
        _make_recording(tmp_path / "_lerobot_exports")  # has an mcap, but reserved name
        _make_recording(tmp_path / "rec")

        entries = scan_output_dir(tmp_path)

        assert [e.name for e in entries] == ["rec"]

    def test_underscore_or_dot_task_name_recording_is_visible(self, tmp_path: Path) -> None:
        """Recordings whose (unsanitized) name starts with _ or . must stay visible."""
        _make_recording(tmp_path / "_calib_20260101")
        _make_recording(tmp_path / ".hidden_20260101")

        names = {e.name for e in scan_output_dir(tmp_path)}

        assert names == {"_calib_20260101", ".hidden_20260101"}

    def test_sorted_by_recording_start_ns_not_mtime(self, tmp_path: Path) -> None:
        """Recording folders are sorted by recording_start_ns descending, not by mtime.

        Regression: sorting purely by st_mtime caused older recordings to be treated as "latest"
        once files were added later (e.g., quality analysis), breaking the UI order.
        Prioritizing recording_start_ns (immutable) fixes this.
        """
        old = _make_recording(
            tmp_path / "old_recording",
            metadata=(
                "rosbag2_bagfile_information:\n"
                "  starting_time:\n"
                "    nanoseconds_since_epoch: 1000\n"
                "  duration:\n"
                "    nanoseconds: 5000\n"
            ),
        )
        new = _make_recording(
            tmp_path / "new_recording",
            metadata=(
                "rosbag2_bagfile_information:\n"
                "  starting_time:\n"
                "    nanoseconds_since_epoch: 9000\n"
                "  duration:\n"
                "    nanoseconds: 5000\n"
            ),
        )
        # Flip mtime: old has the newer mtime
        os.utime(new, (time.time() - 100, time.time() - 100))
        os.utime(old, (time.time(), time.time()))

        entries = scan_output_dir(tmp_path)

        assert entries[0].name == "new_recording"
        assert entries[0].recording_start_ns == 9000
        assert entries[1].name == "old_recording"
        assert entries[1].recording_start_ns == 1000

    def test_sorted_mixed_metadata_and_no_metadata(self, tmp_path: Path) -> None:
        """With-metadata entries (larger recording_start_ns) rank above without-metadata entries (0)."""
        with_meta = _make_recording(
            tmp_path / "with_meta",
            metadata=(
                "rosbag2_bagfile_information:\n"
                "  starting_time:\n"
                "    nanoseconds_since_epoch: 100\n"
                "  duration:\n"
                "    nanoseconds: 5000\n"
            ),
        )
        _make_recording(tmp_path / "without_meta")
        # mtime is more recent on without_meta
        os.utime(with_meta, (time.time() - 100, time.time() - 100))

        entries = scan_output_dir(tmp_path)

        assert entries[0].name == "with_meta"
        assert entries[1].name == "without_meta"

    def test_permission_error(self, tmp_path: Path) -> None:
        """Returns an empty list when a PermissionError is raised."""
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            assert scan_output_dir(restricted) == []

    def test_recording_meta_included(self, tmp_path: Path) -> None:
        """When recording_meta.json exists, task_name / recording_config_name / tags are filled in."""
        rec = _make_recording(tmp_path / "rec")
        (rec / "recording_meta.json").write_text(
            json.dumps({"task_name": "pick", "recording_config_name": "simulator", "tags": ["t1", "t2"]}),
            encoding="utf-8",
        )

        entries = scan_output_dir(tmp_path)

        assert entries[0].task_name == "pick"
        assert entries[0].recording_config_name == "simulator"
        assert entries[0].tags == ["t1", "t2"]

    def test_recording_meta_absent_defaults(self, tmp_path: Path) -> None:
        """For legacy recording folders without recording_meta.json, task_name=None / recording_config_name=None / tags=[]."""
        _make_recording(tmp_path / "rec")

        entries = scan_output_dir(tmp_path)

        assert entries[0].task_name is None
        assert entries[0].recording_config_name is None
        assert entries[0].tags == []


def _make_recording_with_task(folder: Path, task_name: str | None, *, mtime: float | None = None) -> Path:
    """Creates a recording folder containing `.mcap` + recording_meta.json with the given task_name."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "recording_0.mcap").write_bytes(b"x")
    (folder / "recording_meta.json").write_text(
        json.dumps({"task_name": task_name, "recording_config_name": None, "tags": []}),
        encoding="utf-8",
    )
    if mtime is not None:
        os.utime(folder, (mtime, mtime))
    return folder


class TestCollectRecentTaskNames:
    """Tests for collect_recent_task_names."""

    def test_returns_empty_when_output_dir_missing(self, tmp_path: Path) -> None:
        assert collect_recent_task_names(tmp_path / "nonexistent") == []

    def test_returns_empty_when_no_recordings(self, tmp_path: Path) -> None:
        assert collect_recent_task_names(tmp_path) == []

    def test_skips_recordings_without_meta(self, tmp_path: Path) -> None:
        """Skips recording folders without a recording_meta.json."""
        _make_recording(tmp_path / "rec_a")
        assert collect_recent_task_names(tmp_path) == []

    def test_skips_null_and_empty_task_names(self, tmp_path: Path) -> None:
        """Recordings whose task_name is null or empty are excluded."""
        _make_recording_with_task(tmp_path / "rec_a", task_name=None)
        _make_recording_with_task(tmp_path / "rec_b", task_name="")
        assert collect_recent_task_names(tmp_path) == []

    def test_returns_unique_names(self, tmp_path: Path) -> None:
        """Returns each task_name only once."""
        _make_recording_with_task(tmp_path / "rec_a", task_name="pick", mtime=1000.0)
        _make_recording_with_task(tmp_path / "rec_b", task_name="pick", mtime=2000.0)
        _make_recording_with_task(tmp_path / "rec_c", task_name="place", mtime=1500.0)

        names = collect_recent_task_names(tmp_path)

        assert names == ["pick", "place"]

    def test_orders_by_most_recent_use(self, tmp_path: Path) -> None:
        """The most recent use time (folder mtime) comes first."""
        _make_recording_with_task(tmp_path / "rec_a", task_name="older", mtime=1000.0)
        _make_recording_with_task(tmp_path / "rec_b", task_name="newer", mtime=5000.0)
        _make_recording_with_task(tmp_path / "rec_c", task_name="middle", mtime=3000.0)

        names = collect_recent_task_names(tmp_path)

        assert names == ["newer", "middle", "older"]

    def test_ignores_non_directory_entries(self, tmp_path: Path) -> None:
        """Files directly under output_dir are ignored."""
        (tmp_path / "stray.txt").write_text("noise", encoding="utf-8")
        _make_recording_with_task(tmp_path / "rec", task_name="pick", mtime=1000.0)

        assert collect_recent_task_names(tmp_path) == ["pick"]

    def test_ignores_ds_store(self, tmp_path: Path) -> None:
        """.DS_Store directories are ignored."""
        (tmp_path / ".DS_Store").mkdir()
        _make_recording_with_task(tmp_path / "rec", task_name="pick", mtime=1000.0)

        assert collect_recent_task_names(tmp_path) == ["pick"]

    def test_permission_error_returns_empty(self, tmp_path: Path) -> None:
        with patch.object(Path, "iterdir", side_effect=PermissionError("denied")):
            assert collect_recent_task_names(tmp_path) == []

    def test_stat_failure_skips_folder(self, tmp_path: Path) -> None:
        """A stat() failure on one folder is isolated; the rest still load.

        On Python 3.10 ``Path.is_dir()`` itself calls ``stat()``, so patching
        ``stat`` raises through both ``is_dir`` and the explicit ``stat`` call.
        The scanner's try/except must cover both for the failure to be skipped
        cleanly.
        """
        _make_recording_with_task(tmp_path / "rec_ok", task_name="ok", mtime=1000.0)
        bad = _make_recording_with_task(tmp_path / "rec_bad", task_name="bad")

        real_stat = Path.stat

        def selective_stat(self: Path, **kwargs: object) -> os.stat_result:
            if self == bad:
                raise OSError("denied")
            return real_stat(self, **kwargs)  # type: ignore[arg-type]

        with patch.object(Path, "stat", selective_stat):
            names = collect_recent_task_names(tmp_path)

        assert names == ["ok"]

    def test_recent_occurrence_wins_on_dedup(self, tmp_path: Path) -> None:
        """On duplicates, the most recent use (largest mtime) wins and is placed at the front."""
        _make_recording_with_task(tmp_path / "rec_a", task_name="pick", mtime=1000.0)
        _make_recording_with_task(tmp_path / "rec_b", task_name="pick", mtime=9000.0)
        _make_recording_with_task(tmp_path / "rec_c", task_name="place", mtime=5000.0)

        names = collect_recent_task_names(tmp_path)

        assert names == ["pick", "place"]
