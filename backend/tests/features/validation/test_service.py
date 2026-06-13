"""Tests for ValidationService (the API facade)."""

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.jobs.models import JobStatus, JobType, ValidationJob
from app.features.jobs.service import set_job_queue
from app.features.validation.cache import CACHE_FILENAME
from app.features.validation.service import ValidationService, get_validation_service


@pytest.fixture
def mock_queue() -> Iterator[MagicMock]:
    """A mock JobQueue registered as the global singleton for the test."""
    queue = MagicMock()
    queue.enqueue_validation = AsyncMock()
    set_job_queue(queue)
    yield queue
    set_job_queue(None)  # type: ignore[arg-type]


def _make_validation_json(directory: Path) -> None:
    """Write a minimal validation_result.json into `directory`."""
    payload = {
        "overall_status": "pass",
        "results": [],
        "task_name": None,
        "executed_at": "2026-05-25T12:00:00+00:00",
    }
    (directory / CACHE_FILENAME).write_text(json.dumps(payload), encoding="utf-8")


def _make_quality_json(directory: Path) -> None:
    """Write a minimal quality_report.json into `directory`."""
    payload = {
        "duration_sec": 10.0,
        "total_messages": 0,
        "total_topics": 0,
        "file_size_bytes": 0,
        "topics": [],
    }
    (directory / "quality_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_job(target: Path, status: JobStatus, error: str | None = None) -> ValidationJob:
    return ValidationJob(
        job_id="val_test",
        type=JobType.VALIDATION,
        folder=target.name,
        status=status,
        error=error,
        target_path=target,
    )


class TestValidationServiceGet:
    """ValidationService.get() — read-only state lookup."""

    async def test_returns_ready_when_cached(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        _make_validation_json(tmp_path)
        mock_queue.get_active_validation_job.return_value = None

        response = await ValidationService().get(tmp_path)
        assert response.status == "ready"
        assert response.report is not None
        assert response.report.overall_status == "pass"

    async def test_returns_analyzing_when_job_running(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        mock_queue.get_active_validation_job.return_value = _make_job(tmp_path, JobStatus.RUNNING)

        response = await ValidationService().get(tmp_path)
        assert response.status == "analyzing"
        assert response.report is None

    async def test_returns_analyzing_when_job_queued(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        mock_queue.get_active_validation_job.return_value = _make_job(tmp_path, JobStatus.QUEUED)

        response = await ValidationService().get(tmp_path)
        assert response.status == "analyzing"

    async def test_returns_error_when_job_failed(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        mock_queue.get_active_validation_job.return_value = _make_job(tmp_path, JobStatus.FAILED, error="boom")

        response = await ValidationService().get(tmp_path)
        assert response.status == "error"
        assert response.error == "boom"

    async def test_returns_error_with_default_message_when_no_detail(
        self, tmp_path: Path, mock_queue: MagicMock
    ) -> None:
        mock_queue.get_active_validation_job.return_value = _make_job(tmp_path, JobStatus.FAILED, error=None)

        response = await ValidationService().get(tmp_path)
        assert response.status == "error"
        assert response.error == "Validation failed"

    async def test_returns_not_found_when_nothing(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        mock_queue.get_active_validation_job.return_value = None

        response = await ValidationService().get(tmp_path)
        assert response.status == "not_found"
        assert response.report is None


class TestValidationServiceStart:
    """ValidationService.start() — trigger run."""

    async def test_returns_ready_when_cached(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        _make_validation_json(tmp_path)
        mock_queue.get_active_validation_job.return_value = None

        response = await ValidationService().start(tmp_path)
        assert response.status == "ready"
        mock_queue.enqueue_validation.assert_not_called()

    async def test_returns_analyzing_when_job_running(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        mock_queue.get_active_validation_job.return_value = _make_job(tmp_path, JobStatus.RUNNING)

        response = await ValidationService().start(tmp_path)
        assert response.status == "analyzing"
        mock_queue.enqueue_validation.assert_not_called()

    async def test_returns_not_found_without_quality_report(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        """Validation requires the quality report to be already generated."""
        mock_queue.get_active_validation_job.return_value = None

        response = await ValidationService().start(tmp_path)
        assert response.status == "not_found"
        assert response.error is not None
        assert "Quality report" in response.error
        mock_queue.enqueue_validation.assert_not_called()

    async def test_enqueues_when_quality_ready(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        _make_quality_json(tmp_path)
        mock_queue.get_active_validation_job.return_value = None

        response = await ValidationService().start(tmp_path)
        assert response.status == "analyzing"
        mock_queue.enqueue_validation.assert_awaited_once_with(tmp_path)


class TestGetValidationService:
    def test_returns_singleton(self) -> None:
        assert get_validation_service() is get_validation_service()


class TestValidationServiceSchedule:
    """ValidationService.schedule() — used by the post-recording auto-chain."""

    async def test_noop_when_cached(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        _make_validation_json(tmp_path)

        await ValidationService().schedule(tmp_path)
        mock_queue.enqueue_validation.assert_not_called()

    async def test_noop_when_job_running(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        mock_queue.get_active_validation_job.return_value = _make_job(tmp_path, JobStatus.RUNNING)

        await ValidationService().schedule(tmp_path)
        mock_queue.enqueue_validation.assert_not_called()

    async def test_enqueues_otherwise(self, tmp_path: Path, mock_queue: MagicMock) -> None:
        mock_queue.get_active_validation_job.return_value = None

        await ValidationService().schedule(tmp_path)
        mock_queue.enqueue_validation.assert_awaited_once_with(tmp_path)
