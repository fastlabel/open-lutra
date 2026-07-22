"""Subprocess-based ROS2 bag recording.

Records ROS2 topics in a separate process.
Memory is isolated to the subprocess, so long recordings stay safe.
"""

from __future__ import annotations

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

if TYPE_CHECKING:
    from app.infra.ros2.record_process import RecordProcess
    from app.settings import Settings

logger = logging.getLogger(__name__)


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
            raise RecorderError(f"Failed to create output directory: {e}") from e

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

        # Write app-specific metadata (ros2 bag record has already created output_path).
        # On failure, log a warning only and let recording continue.
        self._write_meta(output_path, task_name, metadata)

        self._record = record
        self._current_topics = topics_to_record
        self._output_path = output_path
        self._start_time = datetime.now()

        logger.info("Recording started: path=%s", output_path)
        return output_path

    def _write_meta(
        self, output_path: Path, task_name: str | None, metadata: dict[str, str] | None
    ) -> None:
        """Write recording_meta.json. Logs a warning on failure."""
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
            logger.warning("Failed to write recording_meta.json: %s", e)

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
        logger.error(
            "Recorder process exited abnormally (exit code=%s, path=%s)",
            returncode,
            self._output_path,
        )

        self._record.cleanup()
        self._reset_state()
        self._notify_crash(returncode, output_name)

    @staticmethod
    def _notify_crash(returncode: int, output_name: str) -> None:  # pragma: no cover
        """Report an abnormal termination to LogManager."""
        try:
            from app.shared.log_manager import get_log_manager

            get_log_manager().add(
                "danger",
                f"Recorder process exited abnormally (exit code={returncode}) -> {output_name}",
            )
        except Exception as e:
            # Skip when LogManager is not initialized (e.g. tests); crash notification is non-critical.
            logger.debug("Skipping crash notification because LogManager is not initialized: %s", e)

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
