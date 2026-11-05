"""Shared infrastructure layer for ffmpeg video encoding.

Builds the ffmpeg command lines for preview MP4s and LeRobot export videos,
resolves the configured encoder (CPU libx264 or NVIDIA NVENC), and runs encodes
down a CPU fallback ladder. Features should import only what they need via
`from app.infra.video import ...`.
"""

from app.infra.video.commands import (
    LIBX264,
    NVENC,
    NVENC_GPU_DECODE,
    EncodeStep,
    VideoEncoder,
    export_ladder,
    mjpeg_pipe_command,
    nvenc_probe_command,
    preview_ladder,
    rawvideo_rgb24_command,
)
from app.infra.video.fallback import VideoEncodeError, run_with_fallback
from app.infra.video.probe import effective_encoder, nvenc_usable, resolve_encoder

__all__ = [
    "LIBX264",
    "NVENC",
    "NVENC_GPU_DECODE",
    "EncodeStep",
    "VideoEncodeError",
    "VideoEncoder",
    "effective_encoder",
    "export_ladder",
    "mjpeg_pipe_command",
    "nvenc_probe_command",
    "nvenc_usable",
    "preview_ladder",
    "rawvideo_rgb24_command",
    "resolve_encoder",
    "run_with_fallback",
]
