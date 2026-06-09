"""Construct boto3 S3 clients and TransferConfigs from app settings.

Credential discovery is delegated to boto3:
  - If `aws_profile` is set, build the client via a Session bound to that
    profile.
  - Otherwise, build a default client; boto3 picks credentials up from the
    process env vars (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY).

`endpoint_url` is honored so the same code path works against LocalStack,
MinIO, Cloudflare R2, etc.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import boto3
from boto3.s3.transfer import TransferConfig

if TYPE_CHECKING:
    from app.settings import Settings


def build_s3_client(settings: Settings) -> Any:
    """Return a configured boto3 S3 client."""
    kwargs: dict[str, Any] = {}
    if settings.aws_region:
        kwargs["region_name"] = settings.aws_region
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url

    if settings.aws_profile:
        session = boto3.Session(profile_name=settings.aws_profile)
        return session.client("s3", **kwargs)
    return boto3.client("s3", **kwargs)


def build_transfer_config(settings: Settings) -> TransferConfig:
    """Assemble a TransferConfig from optional env-var overrides.

    Returns boto3's default `TransferConfig()` when no overrides are set, so
    typical users do not need to tune these values.
    """
    kwargs: dict[str, Any] = {}
    mb = 1024 * 1024
    if settings.s3_multipart_threshold_mb is not None:
        kwargs["multipart_threshold"] = settings.s3_multipart_threshold_mb * mb
    if settings.s3_multipart_chunksize_mb is not None:
        kwargs["multipart_chunksize"] = settings.s3_multipart_chunksize_mb * mb
    if settings.s3_max_concurrency is not None:
        kwargs["max_concurrency"] = settings.s3_max_concurrency
    return TransferConfig(**kwargs)
