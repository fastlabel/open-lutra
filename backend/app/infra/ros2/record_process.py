"""Lifecycle control for the recording process.

For a recording process started with --start-paused, send the SPACE key
through the pty and monitor pty output for DDS discovery.

Unified pty I/O:
    Connecting stdin/stdout/stderr to a single pty gives ros2 bag record a
    full TTY environment. As a result:

    1. ros2 bag record's progress display and keyboard control are recognized
       as "interactive mode", matching the behavior of direct terminal execution.
    2. The large burst of cleanup logs after SIGINT no longer blocks on a full
       PIPE buffer, so the process can shut down gracefully until the MCAP
       writer finishes its flush (resolves dropped frames at the tail).
    3. Discovery monitoring, progress logs, and cleanup logs can all be drained
       by a single reader thread.
"""

import contextlib
import fcntl
import logging
import os
import re
import subprocess
import threading
import time

logger = logging.getLogger(__name__)


class RecordProcess:  # pragma: no cover
    """A recording process started with --start-paused.

    Sends the SPACE key via pty to control when recording starts. Starting
    after DDS discovery completes prevents message loss at the beginning of
    the recording.

    The pty master stays open for the entire recording, and a background
    drain thread continuously consumes pty output. This prevents the pty
    buffer from filling up and blocking ros2 bag record's writes (especially
    during the cleanup phase after SIGINT).

    The pty master must stay open for the entire recording.
    Closing the master mid-recording causes EIO (errno=5) on the slave side
    and crashes ros2 bag record's keyboard monitor thread.
    """

    def __init__(self, process: subprocess.Popen[bytes], pty_fd: int) -> None:
        self.process = process
        self._pty_fd = pty_fd
        # Ring buffer and lock for discovery waiting
        self._buffer = bytearray()
        self._buffer_lock = threading.Lock()
        self._stop_drain = threading.Event()
        self._drain_thread: threading.Thread | None = None
        self._start_drain()

    def wait_for_subscriptions(self, topics: list[str], timeout: float) -> list[str]:
        """Watch pty output and wait for topic subscriptions.

        ros2 bag record's logs (stderr) come through the pty, so we parse the
        buffer accumulated by the drain thread while popping it.

        Args:
            topics: Topic names to wait for subscription completion.
            timeout: Maximum wait time in seconds.

        Returns:
            List of topic names that were confirmed subscribed.
        """
        subscribed: set[str] = set()
        expected = set(topics)
        ready_for_input = False
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            # A dead recorder will never subscribe; stop waiting so the caller
            # can report the failure immediately instead of after the timeout.
            if self.process.poll() is not None:
                logger.warning(
                    "Recorder process exited while waiting for DDS discovery (exit code=%s)",
                    self.process.returncode,
                )
                break
            text = self._consume_buffer()
            if text:
                for match in re.finditer(r"Subscribed to topic '([^']+)'", text):
                    topic = match.group(1)
                    if topic not in subscribed:
                        subscribed.add(topic)
                        logger.info("Topic connection confirmed: %s", topic)
                if "Waiting for recording" in text:
                    ready_for_input = True
            # Break once all topics are subscribed and the recorder is waiting for SPACE
            if subscribed >= expected and ready_for_input:
                logger.info("All topic connections confirmed (%d/%d)", len(subscribed), len(expected))
                break
            time.sleep(0.05)

        return sorted(subscribed)

    def resume(self) -> None:
        """Send SPACE to resume recording."""
        os.write(self._pty_fd, b" ")
        logger.info("Sent recording-resume signal (SPACE via pty)")

    def cleanup(self) -> None:
        """Close the pty master (call only after the process has exited).

        Closing the master mid-recording causes EIO (errno=5) on the slave
        side, so this must be called only after the process exits. The drain
        thread is also stopped here.
        """
        self._stop_drain.set()
        if self._drain_thread is not None:
            self._drain_thread.join(timeout=2.0)
            self._drain_thread = None
        with contextlib.suppress(OSError):
            os.close(self._pty_fd)

    def _start_drain(self) -> None:
        """Start a drain thread that continuously reads pty output.

        ros2 bag record emits a large amount of logs to stderr during the
        cleanup phase. Without draining, the pty buffer fills, write blocks,
        and the MCAP writer's flush gets interrupted.
        """
        # Put the pty into non-blocking mode
        fl = fcntl.fcntl(self._pty_fd, fcntl.F_GETFL)
        fcntl.fcntl(self._pty_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        thread = threading.Thread(target=self._drain_loop, name="record-pty-drain", daemon=True)
        thread.start()
        self._drain_thread = thread

    def _drain_loop(self) -> None:
        """Continuously read from the pty fd and accumulate into the buffer."""
        while not self._stop_drain.is_set():
            try:
                data = os.read(self._pty_fd, 4096)
            except BlockingIOError:
                time.sleep(0.02)
                continue
            except OSError:
                # The fd was closed / the process exited
                return
            if not data:
                time.sleep(0.02)
                continue
            with self._buffer_lock:
                self._buffer.extend(data)
                # Only the first few KB are needed for discovery monitoring, so
                # cap the buffer (64 KB) and trim older data to prevent unbounded growth.
                if len(self._buffer) > 65536:
                    del self._buffer[: len(self._buffer) - 32768]

    def _consume_buffer(self) -> str:
        """Pop and return the accumulated buffer."""
        with self._buffer_lock:
            if not self._buffer:
                return ""
            data = bytes(self._buffer)
            self._buffer.clear()
        return data.decode(errors="replace")
