"""Tests for UploadService (the API facade)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.jobs.models import JobStatus, JobType, UploadJob
from app.features.jobs.service import set_job_queue
from app.features.upload.cache import CACHE_FILENAME
from app.features.upload.service import UploadService, get_upload_service, is_upload_enabled
from app.settings import Settings


def _make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "robot_config": "config/simulator.yaml",
        "output_dir": "/tmp",
        "s3_bucket": "lutra-test",
        "s3_key_template": "uploads/{recording_name}.zip",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _write_state(
    directory: Path,
    *,
    status: str,
    destination: str | None = "lutra-test",
    key: str | None = "uploads/rec.zip",
    etag: str | None = '"abc"',
    size_bytes: int | None = 1024,
    bytes_transferred: int = 1024,
    uploaded_at: datetime | None = datetime(2026, 5, 25, 12, 0, 0, tzinfo=timezone.utc),
    error: str | None = None,
) -> None:
    payload = {
        "status": status,
        "destination": destination,
        "key": key,
        "etag": etag,
        "size_bytes": size_bytes,
        "bytes_transferred": bytes_transferred,
        "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
        "error": error,
    }
    (directory / CACHE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


def _make_job(target: Path, status: JobStatus, error: str | None = None) -> UploadJob:
    return UploadJob(
        job_id="upl_test",
        type=JobType.UPLOAD,
        folder=target.name,
        status=status,
        error=error,
        target_path=target,
    )


@pytest.fixture
def mock_queue() -> Iterator[MagicMock]:
    """A mock JobQueue registered as the global singleton for the test."""
    queue = MagicMock()
    queue.enqueue_upload = AsyncMock()
    set_job_queue(queue)
    yield queue
    set_job_queue(None)  # type: ignore[arg-type]


class TestUploadServiceGet:
    """``UploadService.get()`` — read-only state lookup."""

    async def test_returns_uploaded_when_state_uploaded(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        _write_state(tmp_path, status="uploaded")
        mock_queue.get_active_upload_job.return_value = None

        response = await UploadService().get(tmp_path)
        assert response.status == "uploaded"
        assert response.state is not None
        assert response.state.etag == '"abc"'
        assert response.error is None

    async def test_returns_failed_from_persisted_state(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        _write_state(tmp_path, status="failed", error="network down", etag=None, uploaded_at=None)
        mock_queue.get_active_upload_job.return_value = None

        response = await UploadService().get(tmp_path)
        assert response.status == "failed"
        assert response.error == "network down"

    async def test_returns_uploading_when_job_running(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        mock_queue.get_active_upload_job.return_value = _make_job(tmp_path, JobStatus.RUNNING)

        response = await UploadService().get(tmp_path)
        assert response.status == "uploading"
        assert response.state is None

    async def test_returns_uploading_when_job_queued(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        mock_queue.get_active_upload_job.return_value = _make_job(tmp_path, JobStatus.QUEUED)

        response = await UploadService().get(tmp_path)
        assert response.status == "uploading"

    async def test_returns_failed_when_job_failed(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        mock_queue.get_active_upload_job.return_value = _make_job(
            tmp_path,
            JobStatus.FAILED,
            error="boom",
        )

        response = await UploadService().get(tmp_path)
        assert response.status == "failed"
        assert response.error == "boom"

    async def test_returns_failed_with_default_message_when_no_detail(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        mock_queue.get_active_upload_job.return_value = _make_job(
            tmp_path,
            JobStatus.FAILED,
            error=None,
        )

        response = await UploadService().get(tmp_path)
        assert response.status == "failed"
        assert response.error == "Upload failed"

    async def test_returns_not_found_when_nothing(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        mock_queue.get_active_upload_job.return_value = None

        response = await UploadService().get(tmp_path)
        assert response.status == "not_found"
        assert response.state is None


class TestUploadServiceStart:
    """``UploadService.start()`` — trigger upload."""

    async def test_enqueues_when_configured_and_no_active_job(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        mock_queue.get_active_upload_job.return_value = None

        with patch("app.features.upload.service.get_settings", return_value=_make_settings()):
            response = await UploadService().start(tmp_path)

        assert response.status == "uploading"
        mock_queue.enqueue_upload.assert_awaited_once_with(tmp_path)

    async def test_overwrites_existing_uploaded_state(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        """Per issue #6, ``start()`` always enqueues; an existing ``uploaded`` state is no shortcut."""
        _write_state(tmp_path, status="uploaded")
        mock_queue.get_active_upload_job.return_value = None

        with patch("app.features.upload.service.get_settings", return_value=_make_settings()):
            response = await UploadService().start(tmp_path)

        assert response.status == "uploading"
        mock_queue.enqueue_upload.assert_awaited_once_with(tmp_path)

    async def test_returns_uploading_when_job_running(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        mock_queue.get_active_upload_job.return_value = _make_job(tmp_path, JobStatus.RUNNING)

        with patch("app.features.upload.service.get_settings", return_value=_make_settings()):
            response = await UploadService().start(tmp_path)

        assert response.status == "uploading"
        mock_queue.enqueue_upload.assert_not_called()

    async def test_returns_failed_when_destination_unconfigured(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        with patch(
            "app.features.upload.service.get_settings",
            return_value=_make_settings(s3_bucket=None),
        ):
            response = await UploadService().start(tmp_path)

        assert response.status == "failed"
        assert response.error == "S3_BUCKET is not configured"
        mock_queue.enqueue_upload.assert_not_called()

    async def test_returns_failed_when_template_invalid(
        self,
        tmp_path: Path,
        mock_queue: MagicMock,
    ) -> None:
        with patch(
            "app.features.upload.service.get_settings",
            return_value=_make_settings(s3_key_template="bad/{unknown_placeholder}"),
        ):
            response = await UploadService().start(tmp_path)

        assert response.status == "failed"
        assert response.error is not None
        assert "unknown_placeholder" in response.error
        mock_queue.enqueue_upload.assert_not_called()


class TestGetUploadService:
    def test_returns_singleton(self) -> None:
        assert get_upload_service() is get_upload_service()


class TestIsUploadEnabled:
    """``is_upload_enabled()`` — read-only check used by ``/api/config``."""

    def test_true_when_destination_and_template_valid(self) -> None:
        assert is_upload_enabled(_make_settings()) is True

    def test_false_when_bucket_missing(self) -> None:
        assert is_upload_enabled(_make_settings(s3_bucket=None)) is False

    def test_false_when_template_missing(self) -> None:
        assert is_upload_enabled(_make_settings(s3_key_template=None)) is False

    def test_false_when_template_syntax_invalid(self) -> None:
        assert is_upload_enabled(_make_settings(s3_key_template="x/{unknown}")) is False
