"""Tests for the media video_generator helpers."""

from pathlib import Path

from app.features.media.video_generator import list_videos


def test_list_videos_returns_sorted_mp4_names(tmp_path: Path) -> None:
    (tmp_path / "b.mp4").write_bytes(b"")
    (tmp_path / "a.mp4").write_bytes(b"")
    (tmp_path / "notes.txt").write_bytes(b"")
    assert list_videos(tmp_path) == ["a.mp4", "b.mp4"]


def test_list_videos_empty_directory(tmp_path: Path) -> None:
    assert list_videos(tmp_path) == []
