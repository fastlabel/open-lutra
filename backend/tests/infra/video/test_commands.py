"""Tests for the ffmpeg command builders and fallback ladders."""

from pathlib import Path

import pytest

from app.infra.video import (
    LIBX264,
    NVENC,
    NVENC_GPU_DECODE,
    export_ladder,
    mjpeg_pipe_command,
    nvenc_probe_command,
    preview_ladder,
    rawvideo_rgb24_command,
)

_NVENC_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"]


class TestLadders:
    def test_preview_libx264(self) -> None:
        assert preview_ladder("libx264") == (LIBX264,)

    def test_preview_nvenc_falls_back_decode_first_then_encode(self) -> None:
        assert preview_ladder("nvenc") == (NVENC_GPU_DECODE, NVENC, LIBX264)

    def test_export_libx264(self) -> None:
        assert export_ladder("libx264") == (LIBX264,)

    def test_export_nvenc(self) -> None:
        assert export_ladder("nvenc") == (NVENC, LIBX264)

    def test_step_labels(self) -> None:
        assert [str(step) for step in (NVENC_GPU_DECODE, NVENC, LIBX264)] == [
            "gpu-decode + nvenc",
            "cpu-decode + nvenc",
            "cpu-decode + libx264",
        ]


class TestMjpegPipeCommand:
    def test_libx264_matches_the_original_preview_command(self) -> None:
        assert mjpeg_pipe_command(Path("/rec/cam.mp4"), 30, LIBX264) == [
            "ffmpeg", "-y",
            "-f", "image2pipe", "-c:v", "mjpeg", "-r", "30", "-i", "pipe:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            "-loglevel", "warning",
            "/rec/cam.mp4",
        ]  # fmt: skip

    def test_cpu_decode_nvenc(self) -> None:
        assert mjpeg_pipe_command(Path("/rec/cam.mp4"), 30, NVENC) == [
            "ffmpeg", "-y",
            "-f", "image2pipe", "-c:v", "mjpeg", "-r", "30", "-i", "pipe:0",
            *_NVENC_ARGS, "-pix_fmt", "yuv420p", "-r", "30",
            "-loglevel", "warning",
            "/rec/cam.mp4",
        ]  # fmt: skip

    def test_gpu_decode_nvenc(self) -> None:
        assert mjpeg_pipe_command(Path("/rec/cam.mp4"), 30, NVENC_GPU_DECODE) == [
            "ffmpeg", "-y",
            "-xerror", "-hwaccel", "cuda",
            "-f", "image2pipe", "-c:v", "mjpeg", "-r", "30", "-i", "pipe:0",
            *_NVENC_ARGS, "-pix_fmt", "yuv420p", "-r", "30",
            "-loglevel", "warning",
            "/rec/cam.mp4",
        ]  # fmt: skip


class TestRawvideoRgb24Command:
    def test_libx264_matches_the_original_export_command(self) -> None:
        assert rawvideo_rgb24_command(Path("/ds/cam.mp4"), 640, 480, 15, LIBX264) == [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "640x480", "-r", "15", "-i", "pipe:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-loglevel", "warning",
            "/ds/cam.mp4",
        ]  # fmt: skip

    def test_nvenc(self) -> None:
        assert rawvideo_rgb24_command(Path("/ds/cam.mp4"), 640, 480, 15, NVENC) == [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "640x480", "-r", "15", "-i", "pipe:0",
            *_NVENC_ARGS, "-pix_fmt", "yuv420p",
            "-loglevel", "warning",
            "/ds/cam.mp4",
        ]  # fmt: skip

    def test_gpu_decode_rejected(self) -> None:
        with pytest.raises(ValueError, match="no decode stage"):
            rawvideo_rgb24_command(Path("/ds/cam.mp4"), 640, 480, 15, NVENC_GPU_DECODE)


def test_nvenc_probe_command_encodes_one_synthetic_frame_with_nvenc() -> None:
    assert nvenc_probe_command() == [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=256x256:r=1", "-frames:v", "1",
        *_NVENC_ARGS,
        "-f", "null", "-",
    ]  # fmt: skip
