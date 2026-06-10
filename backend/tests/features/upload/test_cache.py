"""Tests for upload_state.json load/save."""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.features.upload.cache import CACHE_FILENAME, load_state, save_state
from app.features.upload.models import UploadState


def _make_state() -> UploadState:
    return UploadState(
        status="uploaded",
        s3_bucket="lutra-test",
        s3_key="prefix/recording.zip",
        etag='"abc-1"',
        size_bytes=1024,
        bytes_transferred=1024,
        uploaded_at=datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
        error=None,
    )


class TestSaveLoad:
    def test_roundtrip(self, tmp_path: Path) -> None:
        original = _make_state()
        save_state(tmp_path, original)

        loaded = load_state(tmp_path)
        assert loaded is not None
        assert loaded.status == "uploaded"
        assert loaded.s3_bucket == "lutra-test"
        assert loaded.s3_key == "prefix/recording.zip"
        assert loaded.etag == '"abc-1"'
        assert loaded.size_bytes == 1024
        assert loaded.bytes_transferred == 1024
        assert loaded.uploaded_at == datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc)
        assert loaded.error is None

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        assert load_state(tmp_path) is None

    def test_load_corrupted_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / CACHE_FILENAME).write_text("{not valid json", encoding="utf-8")
        assert load_state(tmp_path) is None

    def test_load_invalid_schema_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / CACHE_FILENAME).write_text(json.dumps({"unexpected": "field"}), encoding="utf-8")
        assert load_state(tmp_path) is None
