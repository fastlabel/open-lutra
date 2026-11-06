"""Tests for the ffmpeg command builders and the encoder ladder."""

from pathlib import Path

from app.infra.video.commands import (
    encoder_ladder,
    mjpeg_pipe_command,
    nvenc_probe_command,
    rawvideo_rgb24_command,
)

_NVENC_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "28", "-b:v", "0"]


class TestEncoderLadder:
    def test_libx264(self) -> None:
        assert encoder_ladder("libx264") == ("libx264",)

    def test_nvenc_falls_back_to_libx264(self) -> None:
        assert encoder_ladder("nvenc") == ("nvenc", "libx264")


class TestMjpegPipeCommand:
    def test_libx264_matches_the_original_preview_command(self) -> None:
        assert mjpeg_pipe_command(Path("/rec/cam.mp4"), 30, "libx264") == [
            "ffmpeg", "-y",
            "-f", "image2pipe", "-c:v", "mjpeg", "-r", "30", "-i", "pipe:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            "-loglevel", "warning",
            "/rec/cam.mp4",
        ]  # fmt: skip

    def test_nvenc(self) -> None:
        assert mjpeg_pipe_command(Path("/rec/cam.mp4"), 30, "nvenc") == [
            "ffmpeg", "-y",
            "-f", "image2pipe", "-c:v", "mjpeg", "-r", "30", "-i", "pipe:0",
            *_NVENC_ARGS, "-pix_fmt", "yuv420p", "-r", "30",
            "-loglevel", "warning",
            "/rec/cam.mp4",
        ]  # fmt: skip


class TestRawvideoRgb24Command:
    def test_libx264_matches_the_original_export_command(self) -> None:
        assert rawvideo_rgb24_command(Path("/ds/cam.mp4"), 640, 480, 15, "libx264") == [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "640x480", "-r", "15", "-i", "pipe:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-loglevel", "warning",
            "/ds/cam.mp4",
        ]  # fmt: skip

    def test_nvenc(self) -> None:
        assert rawvideo_rgb24_command(Path("/ds/cam.mp4"), 640, 480, 15, "nvenc") == [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "640x480", "-r", "15", "-i", "pipe:0",
            *_NVENC_ARGS, "-pix_fmt", "yuv420p",
            "-loglevel", "warning",
            "/ds/cam.mp4",
        ]  # fmt: skip


def test_nvenc_probe_command_encodes_one_synthetic_frame_with_nvenc() -> None:
    assert nvenc_probe_command() == [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=256x256:r=1", "-frames:v", "1",
        *_NVENC_ARGS,
        "-f", "null", "-",
    ]  # fmt: skip
