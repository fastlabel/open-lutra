"""Tests for the upload-destination Protocol layer."""

from dataclasses import FrozenInstanceError

import pytest

from app.features.upload.destinations.base import UploadResult


class TestUploadResult:
    def test_required_fields(self) -> None:
        result = UploadResult(size_bytes=1024, etag='"abc"')
        assert result.size_bytes == 1024
        assert result.etag == '"abc"'

    def test_etag_can_be_none(self) -> None:
        result = UploadResult(size_bytes=1024, etag=None)
        assert result.etag is None

    def test_is_frozen(self) -> None:
        result = UploadResult(size_bytes=1024, etag=None)
        with pytest.raises(FrozenInstanceError):
            result.size_bytes = 2048  # type: ignore[misc]
