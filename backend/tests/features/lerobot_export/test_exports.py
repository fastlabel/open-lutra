"""Tests for locating exported datasets on disk."""

from pathlib import Path

from app.features.lerobot_export.exports import EXPORTS_DIRNAME, exports_root


def test_exports_root() -> None:
    assert exports_root(Path("/data/output")).name == EXPORTS_DIRNAME
