"""Tests for the disabled (no-op) upload destination."""

from pathlib import Path

import pytest

from app.features.upload.destinations.base import UploadDestination
from app.features.upload.destinations.disabled import DisabledDestination


class TestConfigurationError:
    def test_always_reports_unconfigured(self) -> None:
        assert DisabledDestination().configuration_error() == "UPLOAD_DESTINATION is not configured"

    def test_conforms_to_protocol(self) -> None:
        assert isinstance(DisabledDestination(), UploadDestination)


class TestPrepareTarget:
    def test_raises(self) -> None:
        with pytest.raises(RuntimeError, match="not configured"):
            DisabledDestination().prepare_target("rec_20260101_000000", 0)


class TestUpload:
    def test_raises(self) -> None:
        with pytest.raises(RuntimeError, match="not configured"):
            DisabledDestination().upload(Path("/tmp/nothing.zip"), "key", lambda _: None)
