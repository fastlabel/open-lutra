"""Shared infrastructure layer for ffmpeg video encoding.

Builds the ffmpeg command lines for preview MP4s and LeRobot export videos,
resolves the configured encoder (CPU libx264 or NVIDIA NVENC), and runs encodes
down a CPU fallback ladder. Features should import only what they need via
`from app.infra.video import ...`.
"""

from app.infra.video.commands import (
    VideoEncodeError,
    VideoEncoder,
    encoder_ladder,
    mjpeg_pipe_command,
    rawvideo_rgb24_command,
)
from app.infra.video.fallback import encode_with_fallback, run_with_fallback
from app.infra.video.probe import effective_encoder

__all__ = [
    "VideoEncodeError",
    "VideoEncoder",
    "effective_encoder",
    "encode_with_fallback",
    "encoder_ladder",
    "mjpeg_pipe_command",
    "rawvideo_rgb24_command",
    "run_with_fallback",
]
