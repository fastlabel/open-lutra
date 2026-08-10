"""Unit tests for ROS2BagRecorder."""

import errno
import json
import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.features.recording import (
    AlreadyRecordingError,
    NotRecordingError,
    RecorderError,
    ROS2BagRecorder,
)
from app.features.recording.service import _disk_space_suffix, _format_gb, _free_disk_bytes
from app.infra.ros2 import ROS2CommandError


class TestRecorderInit:
    """Initialization tests."""

    def test_initial_state(self, recorder: ROS2BagRecorder) -> None:
        assert recorder.is_recording is False

    def test_initial_status(self, recorder: ROS2BagRecorder) -> None:
        status = recorder.get_status()
        assert status.is_recording is False
        assert status.output_path is None
        assert status.start_time is None
        assert status.elapsed_sec == 0.0


class TestStart:
    """Tests for start()."""

    def test_start_with_default_topics(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """When no topics are specified, recording starts with default_topics."""
        output = recorder.start()
        assert output.parent == Path("/tmp/test_output")
        mock_ros2.bag_record.assert_called_once()

        call_kwargs = mock_ros2.bag_record.call_args
        assert "/joint_states" in call_kwargs.kwargs["topics"]
        assert "/camera/color/image_raw/compressed" in call_kwargs.kwargs["topics"]
        assert recorder.is_recording is True

    def test_start_with_explicit_topics(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """Starts recording with explicitly specified topics."""
        recorder.start(topics=["/my_topic"])
        call_kwargs = mock_ros2.bag_record.call_args
        assert call_kwargs.kwargs["topics"] == ["/my_topic"]

    def test_start_passes_output_path(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """Verifies the output path is passed to bag_record."""
        recorder.start(topics=["/topic_a", "/topic_b"])
        call_kwargs = mock_ros2.bag_record.call_args
        assert call_kwargs.kwargs["output_path"].parent == Path("/tmp/test_output")

    def test_start_already_recording_raises(self, recorder: ROS2BagRecorder) -> None:
        """Calling start while already recording raises AlreadyRecordingError."""
        recorder.start(topics=["/topic"])
        with pytest.raises(AlreadyRecordingError, match="Already recording"):
            recorder.start(topics=["/topic"])

    def test_start_empty_topics_raises(self, recorder: ROS2BagRecorder) -> None:
        """Empty topics raises RecorderError."""
        with pytest.raises(RecorderError, match="No topics specified"):
            recorder.start(topics=[])

    def test_start_ros2_command_error_raises(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """ROS2CommandError is translated to RecorderError."""
        mock_ros2.bag_record.side_effect = ROS2CommandError("ros2 command not found")
        with pytest.raises(RecorderError, match="ros2 command not found"):
            recorder.start(topics=["/topic"])

    def test_start_mkdir_oserror_raises(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """A failure to create the output directory raises RecorderError."""
        with (
            patch.object(Path, "mkdir", side_effect=OSError("Permission denied")),
            pytest.raises(RecorderError, match="Failed to create output directory"),
        ):
            recorder.start(topics=["/topic"])


class TestStartWithTaskName:
    """Tests for start() with task_name."""

    def test_start_with_task_name(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """When a task name is provided, the output path is prefixed with it."""
        output = recorder.start(topics=["/topic"], task_name="pick-and-place")
        assert output.name.startswith("pick-and-place_")

    def test_start_without_task_name(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """Without a task name, the output path is timestamp-only."""
        output = recorder.start(topics=["/topic"])
        # Timestamp only (YYYYMMDD_HHMMSS format)
        assert len(output.name) == len("20260325_120000")


class TestStartWithQoSOverrides:
    """Tests for start() with QoS overrides."""

    def test_start_with_qos_overrides(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """When QoS overrides are specified, qos_args is passed to bag_record."""
        recorder.start(topics=["/topic"], qos_overrides={"/topic": "reliable"})
        call_kwargs = mock_ros2.bag_record.call_args
        qos_args = call_kwargs.kwargs["qos_args"]
        assert "--qos-profile-overrides-path" in qos_args

    def test_start_without_qos_overrides(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """Without QoS overrides, qos_args is an empty list."""
        recorder.start(topics=["/topic"])
        call_kwargs = mock_ros2.bag_record.call_args
        assert call_kwargs.kwargs["qos_args"] == []

    def test_start_with_empty_qos_overrides(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """An empty QoS overrides dict is ignored."""
        recorder.start(topics=["/topic"], qos_overrides={})
        call_kwargs = mock_ros2.bag_record.call_args
        assert call_kwargs.kwargs["qos_args"] == []

    def test_start_failure_cleans_up_qos_file(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """The QoS override file is cleaned up when bag_record fails."""
        from app.infra.ros2 import ROS2CommandError

        mock_ros2.bag_record.side_effect = ROS2CommandError("command failed")
        with pytest.raises(RecorderError):
            recorder.start(topics=["/topic"], qos_overrides={"/topic": "reliable"})
        # The QoS file is cleaned up
        assert recorder._qos_file is None


class TestStartDiscovery:
    """Tests for waiting on DDS discovery."""

    def test_start_calls_wait_for_subscriptions(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """start() calls wait_for_subscriptions."""
        mock_record = mock_ros2.bag_record.return_value
        mock_record.wait_for_subscriptions.return_value = ["/topic"]

        recorder.start(topics=["/topic"])

        mock_record.wait_for_subscriptions.assert_called_once_with(["/topic"], 10)
        mock_record.resume.assert_called_once()

    def test_start_resumes_even_on_partial_discovery(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """Starts recording even when only some topics could be subscribed."""
        mock_record = mock_ros2.bag_record.return_value
        mock_record.wait_for_subscriptions.return_value = ["/topic_a"]

        recorder.start(topics=["/topic_a", "/topic_b"])

        mock_record.resume.assert_called_once()
        assert recorder.is_recording is True

    def test_start_skips_discovery_when_timeout_zero(self, settings: MagicMock, mock_ros2: MagicMock) -> None:
        """When discovery_timeout=0, recording starts immediately without waiting."""
        settings.recording_discovery_timeout = 0
        rec = ROS2BagRecorder(settings, mock_ros2)
        mock_record = mock_ros2.bag_record.return_value

        rec.start(topics=["/topic"])

        mock_record.wait_for_subscriptions.assert_not_called()
        mock_record.resume.assert_called_once()


class TestStartDelay:
    """Tests for recording_start_delay_sec."""

    def test_start_delay_sleeps_before_resume(self, settings: MagicMock, mock_ros2: MagicMock) -> None:
        """When start_delay_sec > 0, time.sleep is called before resume."""
        settings.recording_start_delay_sec = 2.0
        rec = ROS2BagRecorder(settings, mock_ros2)
        mock_record = mock_ros2.bag_record.return_value

        with patch("app.features.recording.service.time.sleep") as mock_sleep:
            rec.start(topics=["/topic"])

        mock_sleep.assert_called_once_with(2.0)
        mock_record.resume.assert_called_once()

    def test_start_delay_zero_skips_sleep(self, settings: MagicMock, mock_ros2: MagicMock) -> None:
        """When start_delay_sec = 0, time.sleep is not called."""
        settings.recording_start_delay_sec = 0.0
        rec = ROS2BagRecorder(settings, mock_ros2)

        with patch("app.features.recording.service.time.sleep") as mock_sleep:
            rec.start(topics=["/topic"])

        mock_sleep.assert_not_called()

    def test_start_delay_applies_after_discovery(self, settings: MagicMock, mock_ros2: MagicMock) -> None:
        """start_delay_sec is applied after wait_for_subscriptions."""
        settings.recording_start_delay_sec = 1.5
        rec = ROS2BagRecorder(settings, mock_ros2)
        mock_record = mock_ros2.bag_record.return_value
        mock_record.wait_for_subscriptions.return_value = ["/topic"]

        call_order: list[str] = []
        mock_record.wait_for_subscriptions.side_effect = lambda *_a, **_kw: call_order.append("discovery") or ["/topic"]
        mock_record.resume.side_effect = lambda: call_order.append("resume")

        with patch(
            "app.features.recording.service.time.sleep",
            side_effect=lambda _s: call_order.append("sleep"),
        ):
            rec.start(topics=["/topic"])

        assert call_order == ["discovery", "sleep", "resume"]


class TestStop:
    """Tests for stop()."""

    def test_stop_returns_result(self, recorder: ROS2BagRecorder) -> None:
        """A StopResult is returned on stop."""
        recorder.start(topics=["/topic"])
        result = recorder.stop()
        assert result.output_path.parent == Path("/tmp/test_output")
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.end_time >= result.start_time

    def test_stop_sends_sigint(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """SIGINT is sent on stop."""
        mock_record = mock_ros2.bag_record.return_value
        mock_process = mock_record.process

        recorder.start(topics=["/topic"])
        recorder.stop()

        mock_process.send_signal.assert_called_once_with(signal.SIGINT)
        mock_process.wait.assert_called_once_with(timeout=10)

    def test_stop_calls_cleanup(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """The pty master is cleaned up on stop."""
        mock_record = mock_ros2.bag_record.return_value

        recorder.start(topics=["/topic"])
        recorder.stop()

        mock_record.cleanup.assert_called_once()

    def test_stop_kills_on_timeout(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """kill is called on timeout."""
        mock_record = mock_ros2.bag_record.return_value
        mock_process = mock_record.process
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="ros2", timeout=10),
            None,
        ]

        recorder.start(topics=["/topic"])
        recorder.stop()

        mock_process.kill.assert_called_once()

    def test_stop_resets_state(self, recorder: ROS2BagRecorder) -> None:
        """is_recording becomes False after stop."""
        recorder.start(topics=["/topic"])
        assert recorder.is_recording is True
        recorder.stop()
        assert recorder.is_recording is False

    def test_stop_cleans_up_qos_file(self, recorder: ROS2BagRecorder) -> None:
        """The QoS override file is cleaned up on stop."""
        recorder.start(topics=["/topic"], qos_overrides={"/topic": "reliable"})
        assert recorder._qos_file is not None
        recorder.stop()
        assert recorder._qos_file is None

    def test_stop_not_recording_raises(self, recorder: ROS2BagRecorder) -> None:
        """Calling stop while not recording raises NotRecordingError."""
        with pytest.raises(NotRecordingError, match="Not currently recording"):
            recorder.stop()


class TestGetStatus:
    """Tests for get_status()."""

    def test_status_while_recording(self, recorder: ROS2BagRecorder) -> None:
        """Status while recording is correct."""
        recorder.start(topics=["/topic"])
        status = recorder.get_status()
        assert status.is_recording is True
        assert status.output_path is not None
        assert status.start_time is not None
        assert status.elapsed_sec >= 0.0


class TestMetaWrite:
    """Tests for writing recording_meta.json."""

    def test_meta_written_on_start(self, settings: MagicMock, mock_ros2: MagicMock, tmp_path: Path) -> None:
        """On successful start(), recording_meta.json is written to the output folder."""
        settings.output_dir = tmp_path

        # Mock ros2 bag record's behavior of creating the output dir
        def fake_bag_record(output_path: Path, **_: object) -> MagicMock:
            output_path.mkdir(parents=True, exist_ok=True)
            return mock_ros2.bag_record.return_value

        mock_ros2.bag_record.side_effect = fake_bag_record

        rec = ROS2BagRecorder(settings, mock_ros2)
        output = rec.start(
            topics=["/topic"],
            task_name="pick-and-place",
            metadata={"operator_id": "op001", "target_object": "box"},
        )

        meta_path = output / "recording_meta.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["task_name"] == "pick-and-place"
        assert data["recording_config_name"] == "simulator"  # stem of config/simulator.yaml
        assert data["tags"] == []
        assert data["metadata"] == {"operator_id": "op001", "target_object": "box"}

    def test_meta_task_name_none_when_unspecified(
        self, settings: MagicMock, mock_ros2: MagicMock, tmp_path: Path
    ) -> None:
        """When task_name is not specified, task_name in recording_meta.json is null."""
        settings.output_dir = tmp_path

        def fake_bag_record(output_path: Path, **_: object) -> MagicMock:
            output_path.mkdir(parents=True, exist_ok=True)
            return mock_ros2.bag_record.return_value

        mock_ros2.bag_record.side_effect = fake_bag_record

        rec = ROS2BagRecorder(settings, mock_ros2)
        output = rec.start(topics=["/topic"])

        data = json.loads((output / "recording_meta.json").read_text(encoding="utf-8"))
        assert data["task_name"] is None
        # Metadata defaults to an empty object when not provided.
        assert data["metadata"] == {}

    def test_meta_recording_config_name_uses_settings_stem(
        self, settings: MagicMock, mock_ros2: MagicMock, tmp_path: Path
    ) -> None:
        """recording_config_name uses the stem of settings.recording_config."""
        settings.output_dir = tmp_path
        settings.recording_config = "config/myrobot.yaml"

        def fake_bag_record(output_path: Path, **_: object) -> MagicMock:
            output_path.mkdir(parents=True, exist_ok=True)
            return mock_ros2.bag_record.return_value

        mock_ros2.bag_record.side_effect = fake_bag_record

        rec = ROS2BagRecorder(settings, mock_ros2)
        output = rec.start(topics=["/topic"])

        data = json.loads((output / "recording_meta.json").read_text(encoding="utf-8"))
        assert data["recording_config_name"] == "myrobot"

    def test_meta_write_failure_does_not_break_recording(self, recorder: ROS2BagRecorder) -> None:
        """Recording continues even if writing recording_meta.json fails (output dir not created).

        conftest's output_dir=/tmp/test_output exists, but the mock bag_record does not
        create the {recording_id} dir underneath. The write therefore fails with
        FileNotFoundError (an OSError subclass), but the recording itself succeeds.
        """
        recorder.start(topics=["/topic"])
        assert recorder.is_recording is True


class TestDiskHelpers:
    """Tests for the free-disk-space helpers."""

    def test_free_disk_bytes_returns_free_bytes_for_existing_path(self, tmp_path: Path) -> None:
        free = _free_disk_bytes(tmp_path)
        assert free is not None
        assert free > 0

    def test_free_disk_bytes_returns_none_for_missing_path(self, tmp_path: Path) -> None:
        assert _free_disk_bytes(tmp_path / "does-not-exist") is None

    def test_format_gb_formats_decimal_gb(self) -> None:
        assert _format_gb(300_000_000) == "0.3 GB"
        assert _format_gb(5_000_000_000) == "5.0 GB"
        assert _format_gb(0) == "0.0 GB"

    def test_disk_space_suffix_names_free_space_and_path(self) -> None:
        with patch("app.features.recording.service._free_disk_bytes", return_value=300_000_000):
            suffix = _disk_space_suffix(Path("/data/output"))
        assert suffix == " — free disk space: 0.3 GB at /data/output"

    def test_disk_space_suffix_empty_when_free_space_unavailable(self) -> None:
        with patch("app.features.recording.service._free_disk_bytes", return_value=None):
            assert _disk_space_suffix(Path("/data/output")) == ""


class TestDiskFullErrors:
    """Tests for surfacing disk-full failures with explicit messages (issue #72)."""

    def test_start_rejected_when_disk_has_no_free_space(
        self, recorder: ROS2BagRecorder, mock_ros2: MagicMock
    ) -> None:
        """start() on a hard-full output volume fails before launching the recorder."""
        with (
            patch("app.features.recording.service._free_disk_bytes", return_value=0),
            pytest.raises(RecorderError, match="Disk full: no free disk space left"),
        ):
            recorder.start(topics=["/topic"])
        mock_ros2.bag_record.assert_not_called()

    def test_start_allowed_when_free_space_unknown(self, recorder: ROS2BagRecorder) -> None:
        """An uninspectable output volume does not block recording."""
        with patch("app.features.recording.service._free_disk_bytes", return_value=None):
            recorder.start(topics=["/topic"])
        assert recorder.is_recording is True

    def test_start_mkdir_enospc_names_disk_full(self, recorder: ROS2BagRecorder) -> None:
        """An ENOSPC while creating the output directory is reported as a full disk."""
        err = OSError(errno.ENOSPC, "No space left on device")
        with (
            patch.object(Path, "mkdir", side_effect=err),
            pytest.raises(RecorderError, match="Disk full: cannot create the output directory"),
        ):
            recorder.start(topics=["/topic"])

    def test_start_raises_when_recorder_dies_during_startup(
        self, recorder: ROS2BagRecorder, mock_ros2: MagicMock
    ) -> None:
        """A recorder process that dies before start() returns raises RecorderError."""
        mock_record = mock_ros2.bag_record.return_value
        mock_record.process.poll.return_value = 1
        with pytest.raises(RecorderError, match=r"exited during startup \(exit code=1\)"):
            recorder.start(topics=["/topic"])
        assert recorder.is_recording is False
        mock_record.cleanup.assert_called_once()

    def test_startup_death_message_includes_free_space(
        self, recorder: ROS2BagRecorder, mock_ros2: MagicMock
    ) -> None:
        """The startup-death message names the free space of the output volume.

        Free space is small but non-zero (e.g. exhausted inodes), so the
        hard-full pre-check passes and the death is detected after launch.
        """
        mock_ros2.bag_record.return_value.process.poll.return_value = 1
        with (
            patch("app.features.recording.service._free_disk_bytes", return_value=100_000_000),
            pytest.raises(RecorderError, match=r"free disk space: 0\.1 GB"),
        ):
            recorder.start(topics=["/topic"])

    def test_startup_death_cleans_up_qos_file(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """The QoS file is cleaned up when the recorder dies during startup."""
        mock_ros2.bag_record.return_value.process.poll.return_value = 1
        with pytest.raises(RecorderError):
            recorder.start(topics=["/topic"], qos_overrides={"/topic": "reliable"})
        assert recorder._qos_file is None

    def test_meta_write_enospc_notifies_operator(self, recorder: ROS2BagRecorder) -> None:
        """An ENOSPC while writing recording_meta.json produces a danger log entry naming the disk."""
        err = OSError(errno.ENOSPC, "No space left on device")
        with (
            patch("app.features.recording.service.write_recording_meta", side_effect=err),
            patch.object(ROS2BagRecorder, "_notify_log") as notify,
        ):
            recorder.start(topics=["/topic"])
        severity, message = notify.call_args.args
        assert severity == "danger"
        assert "Disk full" in message
        assert recorder.is_recording is True

    def test_meta_write_generic_failure_notifies_operator(self, recorder: ROS2BagRecorder) -> None:
        """Non-ENOSPC meta-write failures also produce a danger log entry."""
        with patch.object(ROS2BagRecorder, "_notify_log") as notify:
            # conftest's mock bag_record does not create the recording dir, so the
            # write fails with FileNotFoundError.
            recorder.start(topics=["/topic"])
        severity, message = notify.call_args.args
        assert severity == "danger"
        assert "Failed to write recording_meta.json" in message

    def test_crash_notification_includes_free_space(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """A mid-recording crash notification names the free space of the output volume."""
        recorder.start(topics=["/topic"])
        mock_ros2.bag_record.return_value.process.poll.return_value = 1
        with (
            patch("app.features.recording.service._free_disk_bytes", return_value=0),
            patch.object(ROS2BagRecorder, "_notify_log") as notify,
        ):
            recorder.get_status()
        severity, message = notify.call_args.args
        assert severity == "danger"
        assert "exited abnormally (exit code=1)" in message
        assert "free disk space: 0.0 GB" in message


class TestDetectCrash:
    """Tests for detecting abnormal process termination."""

    def test_crash_detected_on_get_status(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """Abnormal process termination is detected in get_status() and the state is reset."""
        mock_process = mock_ros2.bag_record.return_value.process
        recorder.start(topics=["/topic"])
        assert recorder.is_recording is True

        # Process exits abnormally (exit code=1)
        mock_process.poll.return_value = 1

        status = recorder.get_status()
        assert status.is_recording is False

    def test_crash_calls_cleanup(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """The pty master is cleaned up when an abnormal exit is detected."""
        mock_record = mock_ros2.bag_record.return_value
        recorder.start(topics=["/topic"])

        mock_record.process.poll.return_value = -9

        recorder.get_status()
        mock_record.cleanup.assert_called_once()

    def test_crash_cleans_up_qos_file(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """The QoS file is also cleaned up when an abnormal exit is detected."""
        mock_record = mock_ros2.bag_record.return_value
        recorder.start(topics=["/topic"], qos_overrides={"/topic": "reliable"})
        assert recorder._qos_file is not None

        mock_record.process.poll.return_value = 1

        recorder.get_status()
        assert recorder._qos_file is None

    def test_no_false_positive_while_running(self, recorder: ROS2BagRecorder, mock_ros2: MagicMock) -> None:
        """poll()=None (still running) is not treated as an abnormal exit."""
        recorder.start(topics=["/topic"])

        # poll() returns None = still running (conftest default)
        status = recorder.get_status()
        assert status.is_recording is True

    def test_no_crash_check_when_not_recording(self, recorder: ROS2BagRecorder) -> None:
        """When not recording, _detect_crash does nothing."""
        status = recorder.get_status()
        assert status.is_recording is False
