"""S3 upload destination.

Wraps boto3's S3 client and managed-transfer API into the
:class:`UploadDestination` protocol. Also supports any S3-compatible
endpoint (MinIO, Cloudflare R2, LocalStack) via ``AWS_ENDPOINT_URL``.

Credential discovery is delegated to boto3:

* When ``aws_profile`` is set, build via a :class:`boto3.Session` bound to
  that profile.
* Otherwise build a default client; boto3 picks credentials up from the
  process env vars (``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import boto3
from boto3.s3.transfer import TransferConfig

from app.features.upload.destinations.base import ProgressCallback, UploadResult
from app.features.upload.key_template import KeyTemplateError, render_key, validate_template

if TYPE_CHECKING:
    from pathlib import Path

    from app.settings import Settings


class S3Destination:
    """Upload to AWS S3 or any S3-compatible endpoint via boto3."""

    name = "s3"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def configuration_error(self) -> str | None:
        if not self._settings.s3_bucket:
            return "S3_BUCKET is not configured"
        if not self._settings.s3_key_template:
            return "S3_KEY_TEMPLATE is not configured"
        try:
            validate_template(self._settings.s3_key_template)
        except KeyTemplateError as e:
            return str(e)
        return None

    def prepare_target(self, recording_name: str, recording_start_ns: int) -> tuple[str, str]:
        bucket = self._settings.s3_bucket
        template = self._settings.s3_key_template
        if bucket is None or template is None:
            # Defensive: configuration_error() should have rejected this upload
            # before prepare_target() is reached.
            raise RuntimeError("S3 destination is not configured")
        key = render_key(
            template,
            recording_name=recording_name,
            recording_start_ns=recording_start_ns,
        )
        return bucket, key

    def upload(
        self,
        local_path: Path,
        key: str,
        progress: ProgressCallback,
    ) -> UploadResult:
        bucket = self._settings.s3_bucket
        if bucket is None:
            # Defensive: the caller is expected to gate on
            # configuration_error(); this guards against programming errors
            # that bypass that contract.
            raise RuntimeError("S3_BUCKET is not configured")

        client = _build_client(self._settings)
        transfer_config = _build_transfer_config(self._settings)
        client.upload_file(
            Filename=str(local_path),
            Bucket=bucket,
            Key=key,
            Config=transfer_config,
            Callback=progress,
        )
        head = client.head_object(Bucket=bucket, Key=key)
        return UploadResult(
            size_bytes=local_path.stat().st_size,
            etag=head.get("ETag"),
        )


def _build_client(settings: Settings) -> Any:
    """Return a configured boto3 S3 client (or session-bound client)."""
    kwargs: dict[str, Any] = {}
    if settings.aws_region:
        kwargs["region_name"] = settings.aws_region
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url

    if settings.aws_profile:
        session = boto3.Session(profile_name=settings.aws_profile)
        return session.client("s3", **kwargs)
    return boto3.client("s3", **kwargs)


def _build_transfer_config(settings: Settings) -> TransferConfig:
    """Assemble a ``TransferConfig`` from optional env-var overrides.

    Returns boto3's default :class:`TransferConfig` when no overrides are
    set, so typical operators do not have to tune these values.
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
