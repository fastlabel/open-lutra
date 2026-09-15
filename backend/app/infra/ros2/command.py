"""Wrapper for ros2 CLI commands.

Hides the execution details of ros2 commands and exposes a simple
interface to the application layer.
"""

import contextlib
import logging
import os
import pty
import subprocess
from pathlib import Path

from app.infra.ros2.record_process import RecordProcess

logger = logging.getLogger(__name__)


class ROS2CommandError(Exception):
    """ros2 command execution error."""


class ROS2Command:
    def bag_record(  # pragma: no cover
        self,
        output_path: Path,
        topics: list[str],
        *,
        qos_args: list[str] | None = None,
    ) -> RecordProcess:
        """Start `ros2 bag record` with --start-paused and return a RecordProcess.

        Starting with --start-paused lets recording wait until DDS discovery
        completes. The caller verifies topic subscriptions via
        wait_for_subscriptions() and then calls resume() to start recording.

        Returns:
            RecordProcess (resume() controls the actual start of recording).

        Raises:
            ROS2CommandError: If the command fails to execute.
        """
        command = [
            "ros2",
            "bag",
            "record",
            "--start-paused",
            "-s",
            "mcap",
            *(qos_args or []),
            "-o",
            str(output_path),
            *topics,
        ]
        logger.info("Starting recording (paused): %s", " ".join(command))

        # Bundle stdin/stdout/stderr onto a single pty to provide a full TTY environment.
        #
        # With PIPE (non-TTY), ros2 bag record reports "Keyboard handling disabled"
        # and the SPACE key needed to leave --start-paused is rejected. Keeping
        # stdout/stderr on PIPE also lets the cleanup-phase log burst fill the
        # PIPE buffer, delaying the MCAP writer flush and dropping frames at the
        # tail of the recording. With pty integration, ros2 bag record sees a
        # full TTY and behaves the same as when run directly in a terminal
        # (tail loss is resolved).
        master_fd, slave_fd = pty.openpty()

        try:
            process = subprocess.Popen(
                command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                # Make the child a new session leader and set its controlling
                # TTY to the pty (works around ros2 bag record's isatty() check).
                start_new_session=True,
            )
        except FileNotFoundError as e:
            os.close(master_fd)
            os.close(slave_fd)
            raise ROS2CommandError("ros2 command not found. Has ROS2 been sourced?") from e
        except OSError as e:
            os.close(master_fd)
            os.close(slave_fd)
            raise ROS2CommandError(f"Failed to start recording: {e}") from e
        finally:
            # The slave was handed to the child, so close it here (finally ensures it is closed).
            with contextlib.suppress(OSError):
                os.close(slave_fd)

        return RecordProcess(process, master_fd)
