"""Per-camera MP4 encoding for LeRobot export.

Holds one ffmpeg process per camera and pipes raw RGB frames to it. All episodes
of one camera are concatenated into a single MP4 (episode boundaries are
recovered from `from_timestamp`/`to_timestamp` in the episodes parquet), so the
processes stay open for the whole export and only one frame per camera is held
in memory at a time.

Encodes h264 / yuv420p to match the codec recorded in `info.json`.

ffmpeg subprocess I/O is excluded from coverage.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class VideoSink:  # pragma: no cover
    """Encodes per-camera RGB frame streams into single MP4 files via ffmpeg."""

    def __init__(self, output_paths: dict[str, Path], image_shapes: dict[str, tuple[int, int, int]], fps: int) -> None:
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self._stderr_threads: list[threading.Thread] = []
        self._stderr_chunks: dict[str, list[bytes]] = {}
        for camera, path in output_paths.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            height, width, _ = image_shapes[camera]
            self._procs[camera] = self._spawn(path, width, height, fps)
            self._stderr_chunks[camera] = []
            self._start_stderr_drain(camera)

    def write(self, camera: str, image: NDArray[np.uint8]) -> None:
        """Pipe one RGB frame to the camera's ffmpeg process."""
        proc = self._procs[camera]
        if proc.stdin is None:
            raise RuntimeError(f"ffmpeg stdin unavailable for camera {camera}")
        proc.stdin.write(np.ascontiguousarray(image, dtype=np.uint8).tobytes())

    def close(self) -> None:
        """Close all stdin pipes and wait for the encoders to finish."""
        for proc in self._procs.values():
            if proc.stdin is not None:
                proc.stdin.close()
            proc.wait(timeout=120)
        for thread in self._stderr_threads:
            thread.join(timeout=5)
        for camera, proc in self._procs.items():
            if proc.returncode != 0:
                stderr = b"".join(self._stderr_chunks[camera]).decode("utf-8", errors="replace")
                raise RuntimeError(f"ffmpeg failed for camera {camera} (code={proc.returncode}): {stderr}")

    def _spawn(self, output_path: Path, width: int, height: int, fps: int) -> subprocess.Popen[bytes]:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(fps),
            "-i",
            "pipe:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-loglevel",
            "warning",
            str(output_path),
        ]
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def _start_stderr_drain(self, camera: str) -> None:
        proc = self._procs[camera]

        def _drain() -> None:
            if proc.stderr is not None:
                self._stderr_chunks[camera].append(proc.stderr.read())

        thread = threading.Thread(target=_drain, daemon=True)
        thread.start()
        self._stderr_threads.append(thread)
