"""ffmpeg command lines for every video the backend encodes.

Two input kinds exist: a JPEG stream piped on stdin (preview MP4s) and raw
RGB24 frames piped on stdin (LeRobot export). Each can be encoded on the CPU
(libx264) or on an NVIDIA GPU (NVENC); the preview path can additionally decode
JPEG on the GPU (NVDEC). An `EncodeStep` names one such combination, and the
ladders list the steps to try in order when GPU encoding is selected.

Every output is H.264 / yuv420p, so the encoder choice never changes what
players or dataset metadata see.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

VideoEncoder = Literal["libx264", "nvenc"]

# NVENC rate control: constant-quality VBR. p4 is NVENC's balanced preset; the
# CQ value keeps file sizes close to libx264's default output.
_NVENC_OUTPUT_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"]
_LIBX264_OUTPUT_ARGS = ["-c:v", "libx264"]


@dataclass(frozen=True)
class EncodeStep:
    """One decode/encode combination of the fallback ladder."""

    encoder: VideoEncoder
    gpu_decode: bool = False

    def __str__(self) -> str:
        return f"{'gpu' if self.gpu_decode else 'cpu'}-decode + {self.encoder}"


LIBX264 = EncodeStep("libx264")
NVENC = EncodeStep("nvenc")
NVENC_GPU_DECODE = EncodeStep("nvenc", gpu_decode=True)


def preview_ladder(encoder: VideoEncoder) -> tuple[EncodeStep, ...]:
    """Steps to try, in order, for a JPEG-stream (preview) encode."""
    if encoder == "nvenc":
        return (NVENC_GPU_DECODE, NVENC, LIBX264)
    return (LIBX264,)


def export_ladder(encoder: VideoEncoder) -> tuple[EncodeStep, ...]:
    """Steps to try, in order, for a raw-RGB (LeRobot export) encode; there is no decode stage."""
    if encoder == "nvenc":
        return (NVENC, LIBX264)
    return (LIBX264,)


def mjpeg_pipe_command(output_path: Path, fps: int, step: EncodeStep) -> list[str]:
    """Command that encodes a JPEG stream on stdin into an H.264 / yuv420p MP4."""
    return [
        "ffmpeg",
        "-y",
        *(["-hwaccel", "cuda"] if step.gpu_decode else []),
        "-f",
        "image2pipe",
        "-c:v",
        "mjpeg",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        *_output_args(step),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-loglevel",
        "warning",
        str(output_path),
    ]


def rawvideo_rgb24_command(output_path: Path, width: int, height: int, fps: int, step: EncodeStep) -> list[str]:
    """Command that encodes raw RGB24 frames on stdin into an H.264 / yuv420p MP4."""
    if step.gpu_decode:
        raise ValueError(f"Raw RGB input has no decode stage to run on the GPU: {step}")
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
        *_output_args(step),
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


def _output_args(step: EncodeStep) -> list[str]:
    return list(_NVENC_OUTPUT_ARGS if step.encoder == "nvenc" else _LIBX264_OUTPUT_ARGS)
