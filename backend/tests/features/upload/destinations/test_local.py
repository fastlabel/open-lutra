"""Tests for the local-filesystem upload destination."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.features.upload.destinations.local import LocalDestination
from app.settings import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"recording_config": "config/simulator.yaml", "output_dir": "/tmp"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestConfigurationError:
    def test_missing_dir(self, tmp_path: Path) -> None:
        destination = LocalDestination(
            _settings(local_upload_path_template="{recording_name}.zip"),
        )
        assert destination.configuration_error() == "LOCAL_UPLOAD_DIR is not configured"

    def test_missing_template(self, tmp_path: Path) -> None:
        destination = LocalDestination(_settings(local_upload_dir=tmp_path))
        assert destination.configuration_error() == "LOCAL_UPLOAD_PATH_TEMPLATE is not configured"

    def test_dir_does_not_exist(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        destination = LocalDestination(
            _settings(
                local_upload_dir=missing,
                local_upload_path_template="{recording_name}.zip",
            ),
        )
        err = destination.configuration_error()
        assert err is not None
        assert "does not exist" in err
        assert str(missing) in err

    def test_dir_not_writable(self, tmp_path: Path) -> None:
        destination = LocalDestination(
            _settings(
                local_upload_dir=tmp_path,
                local_upload_path_template="{recording_name}.zip",
            ),
        )
        with patch("app.features.upload.destinations.local.os.access", return_value=False):
            err = destination.configuration_error()
        assert err is not None
        assert "not writable" in err

    def test_template_with_unknown_placeholder(self, tmp_path: Path) -> None:
        destination = LocalDestination(
            _settings(
                local_upload_dir=tmp_path,
                local_upload_path_template="{unknown}.zip",
            ),
        )
        err = destination.configuration_error()
        assert err is not None
        assert "unknown" in err

    def test_template_with_unbalanced_braces(self, tmp_path: Path) -> None:
        destination = LocalDestination(
            _settings(
                local_upload_dir=tmp_path,
                local_upload_path_template="{recording_name.zip",
            ),
        )
        err = destination.configuration_error()
        assert err is not None
        assert "Unbalanced braces" in err

    def test_all_set(self, tmp_path: Path) -> None:
        destination = LocalDestination(
            _settings(
                local_upload_dir=tmp_path,
                local_upload_path_template="{recording_name}.zip",
            ),
        )
        assert destination.configuration_error() is None


class TestPrepareTarget:
    def test_returns_dir_and_rendered_path(self, tmp_path: Path) -> None:
        destination = LocalDestination(
            _settings(
                local_upload_dir=tmp_path,
                local_upload_path_template="lutra/{yyyymmddhhmmss}/{recording_name}.zip",
            ),
        )
        # 1_700_000_000 s since epoch = 2023-11-14T22:13:20 UTC.
        label, key = destination.prepare_target(
            recording_name="rec_001",
            recording_start_ns=1_700_000_000_000_000_000,
        )
        assert label == str(tmp_path)
        assert key == "lutra/20231114221320/rec_001.zip"

    def test_raises_when_settings_missing(self) -> None:
        """Defensive guard: ``prepare_target`` refuses if configuration was bypassed."""
        destination = LocalDestination(_settings())
        with pytest.raises(RuntimeError, match="not configured"):
            destination.prepare_target(recording_name="r", recording_start_ns=0)


class TestUpload:
    def test_copies_file_and_returns_result(self, tmp_path: Path) -> None:
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        source = source_dir / "rec.zip"
        source.write_bytes(b"x" * 4096)

        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()

        destination = LocalDestination(
            _settings(
                local_upload_dir=upload_dir,
                local_upload_path_template="{recording_name}.zip",
            ),
        )

        progress = MagicMock()
        result = destination.upload(source, "nested/dir/rec.zip", progress)

        target = upload_dir / "nested/dir/rec.zip"
        assert target.is_file()
        assert target.read_bytes() == b"x" * 4096
        assert result.size_bytes == 4096
        assert result.etag is None
        # Single progress callback at completion with the final byte count.
        progress.assert_called_once_with(4096)

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        source = tmp_path / "rec.zip"
        source.write_bytes(b"")
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()
        destination = LocalDestination(
            _settings(
                local_upload_dir=upload_dir,
                local_upload_path_template="{recording_name}.zip",
            ),
        )
        destination.upload(source, "a/b/c/rec.zip", MagicMock())
        assert (upload_dir / "a/b/c/rec.zip").is_file()

    def test_raises_when_dir_unset(self, tmp_path: Path) -> None:
        """Defensive guard: ``upload()`` refuses if a caller bypasses ``configuration_error()``."""
        destination = LocalDestination(_settings())
        with pytest.raises(RuntimeError, match="LOCAL_UPLOAD_DIR"):
            destination.upload(tmp_path / "rec.zip", "rec.zip", MagicMock())
