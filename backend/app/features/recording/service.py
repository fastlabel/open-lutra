"""Subprocess-based ROS2 bag recording.

Records ROS2 topics in a separate process.
Memory is isolated to the subprocess, so long recordings stay safe.
"""

from __future__ import annotations

import errno
import logging
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.features.recording.models import (
    AlreadyRecordingError,
    NotRecordingError,
    RecorderError,
    RecorderStatus,
    StopResult,
)
from app.features.recordings.meta import RecordingMeta, write_recording_meta
from app.infra.ros2 import QoSOverrideFile, ROS2Command, ROS2CommandError
from app.shared.disk import read_disk_usage

if TYPE_CHECKING:
    from app.infra.ros2.record_process import RecordProcess
    from app.settings import Settings
    from app.shared.log_manager import LogSeverity

logger = logging.getLogger(__name__)


def _free_disk_bytes(path: Path) -> int | None:
    """Return the free bytes of the filesystem containing `path`.

    Returns None when the path cannot be inspected (e.g. it does not exist),
    so callers can skip the disk hint instead of failing.
    """
    usage = read_disk_usage(path)
    return usage.free_bytes if usage is not None else None


def _format_gb(num_bytes: int) -> str:
    """Format a byte count as a GB string (e.g. '0.3 GB').

    A GB is 1024**3 here, matching the frontend's formatCapacity/formatSize, so
    the same volume never reads as two different figures across the UI.
    """
    return f"{num_bytes / 1024**3:.1f} GB"


def _disk_space_suffix(path: Path) -> str:
    """Suffix naming the free space at `path` for disk-related error messages.

    Recording failures caused by a full disk are hard to diagnose from generic
    errors, so storage-adjacent messages append the current free space of the
    output volume. Returns ' — free disk space: X GB at <path>', or '' when
    the free space cannot be determined.
    """
    free = _free_disk_bytes(path)
    if free is None:
        return ""
    return f" — free disk space: {_format_gb(free)} at {path}"


class ROS2BagRecorder:
    """Subprocess-based ROS2 bag recording.

    Records topics to MCAP using `ros2 bag record --start-paused -s mcap`.
    `--start-paused` ensures recording begins only after DDS discovery
    completes, preventing message loss at the start of the recording.
    Recording runs in a separate process so its memory usage is
    isolated from the main application.
    """

    def __init__(self, settings: Settings, ros2: ROS2Command) -> None:
        self._output_dir = settings.output_dir
        self._default_topics = settings.default_topics
        self._discovery_timeout = settings.recording_discovery_timeout
        self._start_delay_sec = settings.recording_start_delay_sec
        # Stem of the YAML file path (e.g. "config/simulator.yaml" -> "simulator").
        # Captured at startup and recorded into metadata at recording time.
        self._recording_config_name = Path(settings.recording_config).stem
        self._ros2 = ros2

        self._record: RecordProcess | None = None
        self._current_topics: list[str] | None = None
        self._output_path: Path | None = None
        self._start_time: datetime | None = None
        self._qos_file: QoSOverrideFile | None = None

    @property
    def is_recording(self) -> bool:
        """Return whether a recording is currently in progress."""
        return self._record is not None

    def start(
        self,
        topics: list[str] | None = None,
        qos_overrides: dict[str, str] | None = None,
        task_name: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Path:
        """Start recording ROS2 topics.

        Launches the recorder process with `--start-paused`, then begins
        recording once DDS discovery has confirmed all topic connections
        (or after the discovery timeout elapses).

        Args:
            topics: Topics to record. If None, default_topics is used.
            qos_overrides: Mapping of topic name -> reliability ("reliable"/"best_effort").
                Pass the publisher QoS detected by TopicMonitorService.
            task_name: Task name. When provided, used as a prefix for the directory name.
            metadata: Pre-registered metadata (key -> value) persisted into recording_meta.json.

        Returns:
            The output directory path of the recording.

        Raises:
            AlreadyRecordingError: When a recording is already in progress.
            RecorderError: When recording cannot be started.
        """
        if self._record is not None:
            raise AlreadyRecordingError("Already recording")

        topics_to_record = topics if topics is not None else self._default_topics
        if not topics_to_record:
            raise RecorderError("No topics specified for recording")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        recording_id = f"{task_name}_{timestamp}" if task_name else timestamp
        output_path = self._output_dir / recording_id

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            if e.errno == errno.ENOSPC:
                raise RecorderError(
                    f"Disk full: cannot create the output directory {output_path.parent}. Free up space and try again."
                ) from e
            raise RecorderError(f"Failed to create output directory: {e}") from e

        self._ensure_disk_not_full()

        # Build the QoS override YAML (retained until recording ends).
        self._qos_file = QoSOverrideFile(qos_overrides) if qos_overrides else None
        qos_args = self._qos_file.to_args() if self._qos_file else []

        try:
            record = self._ros2.bag_record(
                output_path=output_path,
                topics=topics_to_record,
                qos_args=qos_args,
            )
        except ROS2CommandError as e:
            if self._qos_file is not None:
                self._qos_file.cleanup()
                self._qos_file = None
            raise RecorderError(str(e)) from e

        # Wait for DDS discovery to complete before starting recording.
        self._wait_and_resume(record, topics_to_record)

        # A recorder that dies this early failed to create the bag (a full disk
        # is the most common cause); report it instead of returning success.
        returncode = record.process.poll()
        if returncode is not None:
            record.cleanup()
            if self._qos_file is not None:
                self._qos_file.cleanup()
                self._qos_file = None
            raise RecorderError(
                f"Recorder process exited during startup (exit code={returncode}); "
                f"no recording was started{_disk_space_suffix(self._output_dir)}. "
                "A full disk is the most common cause; check the backend logs for details."
            )

        # Write app-specific metadata (ros2 bag record has already created output_path).
        # On failure, log a warning only and let recording continue.
        self._write_meta(output_path, task_name, metadata)

        self._record = record
        self._current_topics = topics_to_record
        self._output_path = output_path
        self._start_time = datetime.now()

        logger.info("Recording started: path=%s", output_path)
        return output_path

    def _ensure_disk_not_full(self) -> None:
        """Refuse to start recording when the output volume has no free space left.

        A recorder on a hard-full disk often survives (creating 0-byte files
        still succeeds) and silently records nothing, so this is rejected
        upfront. Skipped when the free space cannot be determined. A
        configurable threshold (recording_min_free_gb) is planned separately.
        """
        if _free_disk_bytes(self._output_dir) == 0:
            raise RecorderError(
                f"Disk full: no free disk space left at {self._output_dir}. "
                "Free up space before starting a recording."
            )

    def _write_meta(
        self, output_path: Path, task_name: str | None, metadata: dict[str, str] | None
    ) -> None:
        """Write recording_meta.json. Reports the failure without aborting the recording."""
        try:
            write_recording_meta(
                output_path,
                RecordingMeta(
                    task_name=task_name,
                    recording_config_name=self._recording_config_name,
                    tags=[],
                    metadata=metadata or {},
                ),
            )
        except OSError as e:
            if e.errno == errno.ENOSPC:
                message = (
                    "Disk full: recording_meta.json could not be written; task name and "
                    f"metadata will be missing{_disk_space_suffix(output_path)}"
                )
            else:
                message = f"Failed to write recording_meta.json: {e}"
            logger.warning(message)
            self._notify_log("danger", message)

    def stop(self) -> StopResult:
        """Stop the current recording.

        Returns:
            A StopResult containing timestamps and path information.

        Raises:
            NotRecordingError: When no recording is in progress.
        """
        if self._record is None:
            raise NotRecordingError("Not currently recording")

        end_time = datetime.now()
        start_time = self._start_time or end_time
        output_path = self._output_path or self._output_dir

        logger.info("Stopping recording: path=%s", output_path)

        try:
            self._record.process.send_signal(signal.SIGINT)
            self._record.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Recorder process did not exit; killing it")
            self._record.process.kill()
            self._record.process.wait()

        # Close the pty master after the process exits.
        # (Closing it while recording is active triggers EIO on the slave side.)
        self._record.cleanup()

        self._reset_state()

        return StopResult(start_time=start_time, end_time=end_time, output_path=output_path)

    def get_status(self) -> RecorderStatus:
        """Return the current recording status.

        Checks process liveness on every call and automatically
        resets internal state if the process has crashed.
        """
        self._detect_crash()

        elapsed = 0.0
        if self._start_time is not None:
            elapsed = (datetime.now() - self._start_time).total_seconds()

        return RecorderStatus(
            is_recording=self.is_recording,
            output_path=self._output_path,
            start_time=self._start_time,
            elapsed_sec=elapsed,
        )

    def _detect_crash(self) -> None:
        """Detect abnormal termination of the recorder process and reset state.

        Called from get_status() so that frontend polling will
        naturally surface a crash.
        """
        if self._record is None:
            return

        returncode = self._record.process.poll()
        if returncode is None:
            return  # Still running

        output_name = self._output_path.name if self._output_path else "unknown"
        # Include free space so a crash caused by a full disk names the cause.
        disk_hint = _disk_space_suffix(self._output_dir)
        logger.error(
            "Recorder process exited abnormally (exit code=%s, path=%s)%s",
            returncode,
            self._output_path,
            disk_hint,
        )

        self._record.cleanup()
        self._reset_state()
        self._notify_log(
            "danger",
            f"Recorder process exited abnormally (exit code={returncode}) -> {output_name}{disk_hint}",
        )

    @staticmethod
    def _notify_log(severity: LogSeverity, message: str) -> None:  # pragma: no cover
        """Report a recording problem to the operator-visible LogManager."""
        try:
            from app.shared.log_manager import get_log_manager

            get_log_manager().add(severity, message)
        except Exception as e:
            # Skip when LogManager is not initialized (e.g. tests); the notification is non-critical.
            logger.debug("Skipping log notification because LogManager is not initialized: %s", e)

    def _wait_and_resume(self, record: RecordProcess, topics: list[str]) -> None:
        """Wait for DDS discovery to complete, then resume the recording.

        Uses RecordProcess.wait_for_subscriptions() to wait for topic
        connections, applies the additional delay configured by
        recording_start_delay_sec, then calls resume() to start recording.
        When discovery_timeout=0, the subscription wait is skipped
        (start_delay is still applied).

        recording_start_delay_sec is used to absorb the lag between a
        camera driver (e.g. RealSense) starting its stream and publishing
        the first frame.
        """
        timeout = self._discovery_timeout

        if timeout > 0:
            subscribed = record.wait_for_subscriptions(topics, timeout)
            if len(subscribed) < len(topics):
                missing = set(topics) - set(subscribed)
                logger.warning(
                    "DDS discovery timeout (%ds): unconnected topics %s",
                    timeout,
                    missing,
                )

        if self._start_delay_sec > 0:
            logger.info(
                "Delaying recording start by %.2f s (waiting for camera publish ramp-up)", self._start_delay_sec
            )
            time.sleep(self._start_delay_sec)

        record.resume()

    def _reset_state(self) -> None:
        """Reset internal state after a recording has stopped."""
        self._record = None
        self._current_topics = None
        self._output_path = None
        self._start_time = None
        if self._qos_file is not None:
            self._qos_file.cleanup()
            self._qos_file = None
