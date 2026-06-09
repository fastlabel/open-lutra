"""Tests for the boto3 S3 client / TransferConfig factory."""

from unittest.mock import MagicMock, patch

from app.features.upload.s3_client import build_s3_client, build_transfer_config
from app.settings import Settings


def _settings(**overrides: object) -> Settings:
    # robot_config / output_dir are required by the project's Settings but
    # irrelevant to the S3 client; supply placeholders so the tests focus on
    # the S3 surface only.
    base: dict[str, object] = {"robot_config": "config/simulator.yaml", "output_dir": "/tmp"}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class TestBuildS3Client:
    def test_default_env_var_path(self) -> None:
        with patch("app.features.upload.s3_client.boto3") as boto3_mock:
            build_s3_client(_settings(aws_region="us-east-1"))
        boto3_mock.client.assert_called_once_with("s3", region_name="us-east-1")
        boto3_mock.Session.assert_not_called()

    def test_profile_path(self) -> None:
        with patch("app.features.upload.s3_client.boto3") as boto3_mock:
            session = MagicMock()
            boto3_mock.Session.return_value = session
            build_s3_client(_settings(aws_profile="dev", aws_region="us-west-2"))
        boto3_mock.Session.assert_called_once_with(profile_name="dev")
        session.client.assert_called_once_with("s3", region_name="us-west-2")
        boto3_mock.client.assert_not_called()

    def test_endpoint_url_applied(self) -> None:
        with patch("app.features.upload.s3_client.boto3") as boto3_mock:
            build_s3_client(_settings(aws_endpoint_url="http://localhost:4566"))
        boto3_mock.client.assert_called_once_with("s3", endpoint_url="http://localhost:4566")

    def test_no_region_or_endpoint(self) -> None:
        """Both omitted: boto3.client is called without kwargs."""
        with patch("app.features.upload.s3_client.boto3") as boto3_mock:
            build_s3_client(_settings())
        boto3_mock.client.assert_called_once_with("s3")


class TestBuildTransferConfig:
    def test_returns_defaults_when_no_overrides(self) -> None:
        config = build_transfer_config(_settings())
        # boto3 defaults: multipart_threshold = 8 MB
        assert config.multipart_threshold == 8 * 1024 * 1024

    def test_honors_threshold_override(self) -> None:
        config = build_transfer_config(_settings(s3_multipart_threshold_mb=64))
        assert config.multipart_threshold == 64 * 1024 * 1024

    def test_honors_chunksize_override(self) -> None:
        config = build_transfer_config(_settings(s3_multipart_chunksize_mb=16))
        assert config.multipart_chunksize == 16 * 1024 * 1024

    def test_honors_concurrency_override(self) -> None:
        config = build_transfer_config(_settings(s3_max_concurrency=12))
        assert config.max_concurrency == 12
