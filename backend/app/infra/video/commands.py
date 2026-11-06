"""ffmpeg command lines for every video the backend encodes.

Two input kinds exist: a JPEG stream piped on stdin (preview MP4s) and raw
RGB24 frames piped on stdin (LeRobot export). Each can be encoded on the CPU
(libx264) or on an NVIDIA GPU (NVENC); JPEG decoding always runs on the CPU.
`encoder_ladder` lists the encoders to try in order.

Every output is H.264 / yuv420p, so the encoder choice never changes what
players or dataset metadata see.
"""

from pathlib import Path
from typing import Literal

VideoEncoder = Literal["libx264", "nvenc"]


class VideoEncodeError(RuntimeError):
    """An ffmpeg encode failed (non-zero exit, or ffmpeg stopped reading its input)."""


# NVENC rate control: constant-quality VBR with NVENC's balanced preset p4.
# CQ 28 keeps file size close to libx264's default output (CRF 23) at equal or
# better SSIM; slower presets, B-frames, lookahead and AQ did not shrink files further.
_NVENC_OUTPUT_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "28", "-b:v", "0"]
_LIBX264_OUTPUT_ARGS = ["-c:v", "libx264"]


def encoder_ladder(encoder: VideoEncoder) -> tuple[VideoEncoder, ...]:
    """Encoders to try, in order: the configured one, then libx264 as the CPU fallback."""
    if encoder == "nvenc":
        return ("nvenc", "libx264")
    return ("libx264",)


def mjpeg_pipe_command(output_path: Path, fps: int, encoder: VideoEncoder) -> list[str]:
    """Command that encodes a JPEG stream on stdin into an H.264 / yuv420p MP4."""
    return [
        "ffmpeg",
        "-y",
        "-f",
        "image2pipe",
        "-c:v",
        "mjpeg",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        *_output_args(encoder),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-loglevel",
        "warning",
        str(output_path),
    ]


def rawvideo_rgb24_command(output_path: Path, width: int, height: int, fps: int, encoder: VideoEncoder) -> list[str]:
    """Command that encodes raw RGB24 frames on stdin into an H.264 / yuv420p MP4."""
    return [
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
        *_output_args(encoder),
        "-pix_fmt",
        "yuv420p",
        "-loglevel",
        "warning",
        str(output_path),
    ]


def nvenc_probe_command() -> list[str]:
    """Command that encodes one synthetic frame with NVENC; exits 0 only if NVENC is usable."""
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=256x256:r=1",
        "-frames:v",
        "1",
        *_NVENC_OUTPUT_ARGS,
        "-f",
        "null",
        "-",
    ]


def _output_args(encoder: VideoEncoder) -> list[str]:
    return list(_NVENC_OUTPUT_ARGS if encoder == "nvenc" else _LIBX264_OUTPUT_ARGS)
