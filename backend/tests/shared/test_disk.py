"""Tests for filesystem capacity inspection."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.shared.disk import read_disk_usage


class TestReadDiskUsage:
    """Tests for read_disk_usage()."""

    def test_returns_capacity_for_existing_path(self, tmp_path: Path) -> None:
        usage = read_disk_usage(tmp_path)
        assert usage is not None
        assert usage.total_bytes > 0
        assert usage.free_bytes > 0
        assert usage.used_bytes >= 0

    def test_maps_the_three_byte_counts(self, tmp_path: Path) -> None:
        """The dataclass mirrors shutil's total / used / free."""
        stat = SimpleNamespace(total=300, used=100, free=180)
        with patch("app.shared.disk.shutil.disk_usage", return_value=stat):
            usage = read_disk_usage(tmp_path)
        assert usage is not None
        assert (usage.total_bytes, usage.used_bytes, usage.free_bytes) == (300, 100, 180)

    def test_returns_none_for_missing_path(self, tmp_path: Path) -> None:
        assert read_disk_usage(tmp_path / "does-not-exist") is None
