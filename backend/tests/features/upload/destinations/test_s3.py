"""Tests for the S3 upload destination."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.features.upload.destinations.s3 import (
    S3Destination,
    _build_client,
    _build_transfer_config,
)
from app.settings import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {"recording_config": "config/simulator.yaml", "output_dir": "/tmp"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestConfigurationError:
    def test_missing_bucket(self) -> None:
        destination = S3Destination(_settings(s3_key_template="x/{recording_name}.zip"))
        assert destination.configuration_error() == "S3_BUCKET is not configured"

    def test_missing_template(self) -> None:
        destination = S3Destination(_settings(s3_bucket="lutra"))
        assert destination.configuration_error() == "S3_KEY_TEMPLATE is not configured"

    def test_both_set(self) -> None:
        destination = S3Destination(
            _settings(s3_bucket="lutra", s3_key_template="x/{recording_name}.zip"),
        )
        assert destination.configuration_error() is None


class TestUpload:
    def test_uploads_and_returns_result(self, tmp_path: Path) -> None:
        local = tmp_path / "rec.zip"
        local.write_bytes(b"x" * 1234)

        with patch("app.features.upload.destinations.s3.boto3") as boto3_mock:
            client = MagicMock()
            client.head_object.return_value = {"ETag": '"abc-1"'}
            boto3_mock.client.return_value = client

            destination = S3Destination(
                _settings(s3_bucket="lutra", s3_key_template="x/{recording_name}.zip"),
            )
            progress = MagicMock()
            result = destination.upload(local, "x/rec.zip", progress)

        client.upload_file.assert_called_once()
        kwargs = client.upload_file.call_args.kwargs
        assert kwargs["Filename"] == str(local)
        assert kwargs["Bucket"] == "lutra"
        assert kwargs["Key"] == "x/rec.zip"
        assert kwargs["Callback"] is progress
        client.head_object.assert_called_once_with(Bucket="lutra", Key="x/rec.zip")
        assert result.size_bytes == 1234
        assert result.etag == '"abc-1"'

    def test_head_object_without_etag(self, tmp_path: Path) -> None:
        """Some storage classes omit ``ETag`` from HEAD; result.etag should be ``None``."""
        local = tmp_path / "rec.zip"
        local.write_bytes(b"")

        with patch("app.features.upload.destinations.s3.boto3") as boto3_mock:
            client = MagicMock()
            client.head_object.return_value = {}
            boto3_mock.client.return_value = client

            destination = S3Destination(
                _settings(s3_bucket="lutra", s3_key_template="x/{recording_name}.zip"),
            )
            result = destination.upload(local, "x/rec.zip", MagicMock())

        assert result.etag is None

    def test_raises_when_bucket_unset(self, tmp_path: Path) -> None:
        """Defensive guard: ``upload()`` refuses if a caller bypasses ``configuration_error()``."""
        destination = S3Destination(_settings())
        with pytest.raises(RuntimeError, match="S3_BUCKET"):
            destination.upload(tmp_path / "rec.zip", "x/rec.zip", MagicMock())


class TestBuildClient:
    def test_default_env_var_path(self) -> None:
        with patch("app.features.upload.destinations.s3.boto3") as boto3_mock:
            _build_client(_settings(aws_region="us-east-1"))
        boto3_mock.client.assert_called_once_with("s3", region_name="us-east-1")
        boto3_mock.Session.assert_not_called()

    def test_profile_path(self) -> None:
        with patch("app.features.upload.destinations.s3.boto3") as boto3_mock:
            session = MagicMock()
            boto3_mock.Session.return_value = session
            _build_client(_settings(aws_profile="dev", aws_region="us-west-2"))
        boto3_mock.Session.assert_called_once_with(profile_name="dev")
        session.client.assert_called_once_with("s3", region_name="us-west-2")
        boto3_mock.client.assert_not_called()

    def test_endpoint_url_applied(self) -> None:
        with patch("app.features.upload.destinations.s3.boto3") as boto3_mock:
            _build_client(_settings(aws_endpoint_url="http://localhost:4566"))
        boto3_mock.client.assert_called_once_with("s3", endpoint_url="http://localhost:4566")

    def test_no_region_or_endpoint(self) -> None:
        with patch("app.features.upload.destinations.s3.boto3") as boto3_mock:
            _build_client(_settings())
        boto3_mock.client.assert_called_once_with("s3")


class TestBuildTransferConfig:
    def test_returns_defaults_when_no_overrides(self) -> None:
        config = _build_transfer_config(_settings())
        assert config.multipart_threshold == 8 * 1024 * 1024

    def test_honors_threshold_override(self) -> None:
        config = _build_transfer_config(_settings(s3_multipart_threshold_mb=64))
        assert config.multipart_threshold == 64 * 1024 * 1024

    def test_honors_chunksize_override(self) -> None:
        config = _build_transfer_config(_settings(s3_multipart_chunksize_mb=16))
        assert config.multipart_chunksize == 16 * 1024 * 1024

    def test_honors_concurrency_override(self) -> None:
        config = _build_transfer_config(_settings(s3_max_concurrency=12))
        assert config.max_concurrency == 12
