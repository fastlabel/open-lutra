"""Per-camera MP4 encoding for LeRobot export.

Holds one ffmpeg process per camera and pipes raw RGB frames to it. All episodes
of one camera are concatenated into a single MP4 (episode boundaries are
recovered from `from_timestamp`/`to_timestamp` in the episodes parquet), so the
processes stay open for the whole export and only one frame per camera is held
in memory at a time.

Encodes h264 / yuv420p to match the codec recorded in `info.json`, with the
given encoder (see `app.infra.video`).

ffmpeg subprocess I/O is excluded from coverage.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.infra.video import VideoEncodeError, VideoEncoder, rawvideo_rgb24_command

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class VideoSink:  # pragma: no cover
    """Encodes per-camera RGB frame streams into single MP4 files via ffmpeg."""

    def __init__(
        self,
        output_paths: dict[str, Path],
        image_shapes: dict[str, tuple[int, int, int]],
        fps: int,
        encoder: VideoEncoder,
    ) -> None:
        self._encoder = encoder
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self._stderr_threads: dict[str, threading.Thread] = {}
        self._stderr_chunks: dict[str, list[bytes]] = {}
        for camera, path in output_paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            height, width, _ = image_shapes[camera]
            self._procs[camera] = self._spawn(path, width, height, fps)
            self._stderr_chunks[camera] = []
            self._start_stderr_drain(camera)

    def write(self, camera: str, image: NDArray[np.uint8]) -> None:
        """Pipe one RGB frame to the camera's ffmpeg process.

        Raises:
            VideoEncodeError: If ffmpeg has exited (e.g. the GPU encoder could
                not start); the message carries ffmpeg's exit code and stderr.
        """
        proc = self._procs[camera]
        if proc.stdin is None:
            raise RuntimeError(f"ffmpeg stdin unavailable for camera {camera}")
        try:
            proc.stdin.write(np.ascontiguousarray(image, dtype=np.uint8).tobytes())
        except BrokenPipeError as e:
            # The pipe broke because ffmpeg is exiting; if it lingers (e.g. GPU
            # teardown), kill it so this still surfaces as an encoder failure.
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            self._stderr_threads[camera].join(timeout=5)
            stderr = b"".join(self._stderr_chunks[camera]).decode("utf-8", errors="replace")
            raise VideoEncodeError(
                f"Video encoding failed ({self._encoder}):\n{camera}: ffmpeg exited {proc.returncode}: {stderr}"
            ) from e

    def close(self) -> None:
        """Finalize all encoders: close every stdin, wait, then check exit codes.

        All stdins are closed up front so one slow/broken encoder cannot leave the
        others blocked on input. A wait timeout escalates to kill() for that
        process. Raises a single error summarizing any non-zero exits.
        """
        for proc in self._procs.values():
            if proc.stdin is not None:
                with contextlib.suppress(OSError):
                    proc.stdin.close()

        errors: list[str] = []
        for camera, proc in self._procs.items():
            try:
                proc.wait(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                errors.append(f"{camera}: ffmpeg timed out")

        for thread in self._stderr_threads.values():
            thread.join(timeout=5)

        for camera, proc in self._procs.items():
            if proc.returncode:  # non-zero / non-None
                stderr = b"".join(self._stderr_chunks[camera]).decode("utf-8", errors="replace")
                errors.append(f"{camera}: ffmpeg exited {proc.returncode}: {stderr}")
        if errors:
            raise VideoEncodeError(f"Video encoding failed ({self._encoder}):\n" + "\n".join(errors))

    def kill(self) -> None:
        """Terminate all encoders immediately without waiting (failure cleanup).

        Best-effort and never raises, so it can run while another exception
        propagates. Closes stdins and kills every process.
        """
        for proc in self._procs.values():
            with contextlib.suppress(Exception):
                if proc.stdin is not None:
                    proc.stdin.close()
                proc.kill()

    def _spawn(self, output_path: Path, width: int, height: int, fps: int) -> subprocess.Popen[bytes]:
        cmd = rawvideo_rgb24_command(output_path, width, height, fps, self._encoder)
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def _start_stderr_drain(self, camera: str) -> None:
        proc = self._procs[camera]

        def _drain() -> None:
            if proc.stderr is not None:
                self._stderr_chunks[camera].append(proc.stderr.read())

        thread = threading.Thread(target=_drain, daemon=True)
        thread.start()
        self._stderr_threads[camera] = thread
