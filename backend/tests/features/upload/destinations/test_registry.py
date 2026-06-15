"""Tests for the upload-destination registry."""

from app.features.upload.destinations import get_active_destination
from app.features.upload.destinations.base import UploadDestination
from app.features.upload.destinations.local import LocalDestination
from app.features.upload.destinations.s3 import S3Destination
from app.settings import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"recording_config": "config/simulator.yaml", "output_dir": "/tmp"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestGetActiveDestination:
    def test_returns_s3_destination_by_default(self) -> None:
        destination = get_active_destination(_settings())
        assert isinstance(destination, S3Destination)

    def test_returns_s3_destination_when_explicitly_selected(self) -> None:
        destination = get_active_destination(_settings(upload_destination="s3"))
        assert isinstance(destination, S3Destination)

    def test_returns_local_destination_when_selected(self) -> None:
        destination = get_active_destination(_settings(upload_destination="local"))
        assert isinstance(destination, LocalDestination)

    def test_conforms_to_protocol(self) -> None:
        """``isinstance`` works because :class:`UploadDestination` is ``@runtime_checkable``."""
        assert isinstance(get_active_destination(_settings()), UploadDestination)
        assert isinstance(
            get_active_destination(_settings(upload_destination="local")),
            UploadDestination,
        )
