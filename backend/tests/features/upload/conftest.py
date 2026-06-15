"""Shared fixtures for upload-feature tests."""

import pytest

# Vars whose corresponding `Settings` fields would otherwise be populated
# from the dev container's .env, contaminating tests that exercise the
# unset / default code paths.
_UPLOAD_ENV_VARS = (
    "UPLOAD_DESTINATION",
    "S3_BUCKET",
    "S3_KEY_TEMPLATE",
    "AWS_REGION",
    "AWS_PROFILE",
    "AWS_ENDPOINT_URL",
    "S3_MULTIPART_THRESHOLD_MB",
    "S3_MULTIPART_CHUNKSIZE_MB",
    "S3_MAX_CONCURRENCY",
    "LOCAL_UPLOAD_DIR",
    "LOCAL_UPLOAD_PATH_TEMPLATE",
)


@pytest.fixture(autouse=True)
def _clear_upload_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _UPLOAD_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
