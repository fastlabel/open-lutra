"""Tests for filesystem free-space inspection."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.shared.disk import read_free_bytes


class TestReadFreeBytes:
    """Tests for read_free_bytes()."""

    def test_returns_free_space_for_existing_path(self, tmp_path: Path) -> None:
        free = read_free_bytes(tmp_path)
        assert free is not None
        assert free >= 0

    def test_reports_the_blocks_available_to_an_unprivileged_process(self, tmp_path: Path) -> None:
        """`free` is used rather than `total - used`, which would include the reserve."""
        stat = SimpleNamespace(total=300, used=100, free=180)
        with patch("app.shared.disk.shutil.disk_usage", return_value=stat):
            assert read_free_bytes(tmp_path) == 180

    def test_returns_none_for_missing_path(self, tmp_path: Path) -> None:
        assert read_free_bytes(tmp_path / "does-not-exist") is None
