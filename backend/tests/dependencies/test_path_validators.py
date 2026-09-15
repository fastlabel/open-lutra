"""Dependency tests for path validation."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.dependencies.path_validators import require_dir, resolve_safe_path


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Test output directory."""
    return tmp_path


class TestResolveSafePath:
    """Tests for resolve_safe_path()."""

    def test_valid_relative_path(self, output_dir: Path) -> None:
        """A valid relative path is resolved."""
        (output_dir / "recording_001").mkdir()

        with patch("app.dependencies.path_validators.get_settings") as mock_settings:
            mock_settings.return_value.output_dir = output_dir
            result = resolve_safe_path(path="recording_001")
            assert result == (output_dir / "recording_001").resolve()

    def test_path_traversal_blocked(self, output_dir: Path) -> None:
        """Path traversal (../) is blocked."""
        with patch("app.dependencies.path_validators.get_settings") as mock_settings:
            mock_settings.return_value.output_dir = output_dir
            with pytest.raises(HTTPException) as exc_info:
                resolve_safe_path(path="../../etc/passwd")
            assert exc_info.value.status_code == 400
            assert "Invalid path" in exc_info.value.detail


class TestRequireDir:
    """Tests for require_dir()."""

    def test_existing_directory(self, tmp_path: Path) -> None:
        """An existing directory is returned as-is."""
        result = require_dir(target=tmp_path)
        assert result == tmp_path

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        """A nonexistent path returns 404."""
        with pytest.raises(HTTPException) as exc_info:
            require_dir(target=tmp_path / "nonexistent")
        assert exc_info.value.status_code == 404

    def test_file_not_directory(self, tmp_path: Path) -> None:
        """A file is not a directory, so it returns 404."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        with pytest.raises(HTTPException) as exc_info:
            require_dir(target=file_path)
        assert exc_info.value.status_code == 404
