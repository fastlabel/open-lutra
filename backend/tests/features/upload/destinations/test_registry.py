"""Tests for the upload-destination registry."""

from app.features.upload.destinations import get_active_destination
from app.features.upload.destinations.base import UploadDestination
from app.features.upload.destinations.s3 import S3Destination
from app.settings import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"recording_config": "config/simulator.yaml", "output_dir": "/tmp"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestGetActiveDestination:
    def test_returns_s3_destination(self) -> None:
        destination = get_active_destination(_settings())
        assert isinstance(destination, S3Destination)

    def test_conforms_to_protocol(self) -> None:
        """``isinstance`` works because :class:`UploadDestination` is ``@runtime_checkable``."""
        destination = get_active_destination(_settings())
        assert isinstance(destination, UploadDestination)
