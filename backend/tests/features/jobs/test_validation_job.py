"""Tests for the validation-related parts of the JobQueue.

These cover only the validation-specific enqueue / discovery / runner paths.
The rest of JobQueue (media / quality / timeline) keeps its existing
testing strategy.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest

from app.features.jobs.models import JobStatus, JobType, ValidationJob
from app.features.jobs.service import JobQueue
from app.features.validation import (
    RecordingValidator,
    ValidationContext,
    ValidationResult,
    register_validator,
)
from app.features.validation.cache import CACHE_FILENAME, load_report
from app.features.validation.registry import clear_registry


@pytest.fixture(autouse=True)
def _clear_validator_registry() -> Iterator[None]:
    """Custom validator registry must be empty between tests."""
    clear_registry()
    yield
    clear_registry()


def _write_quality_report(directory: Path, *, duration_sec: float = 60.0) -> None:
    payload = {
        "duration_sec": duration_sec,
        "total_messages": 0,
        "total_topics": 0,
        "file_size_bytes": 0,
        "topics": [],
    }
    (directory / "quality_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_meta(directory: Path, *, task_name: str | None) -> None:
    payload = {"task_name": task_name, "recording_config_name": None, "tags": []}
    (directory / "recording_meta.json").write_text(json.dumps(payload), encoding="utf-8")


class TestEnqueueValidation:
    async def test_enqueue_creates_active_job(self, tmp_path: Path) -> None:
        queue = JobQueue()
        job = await queue.enqueue_validation(tmp_path)

        assert isinstance(job, ValidationJob)
        assert job.type == JobType.VALIDATION
        assert job.target_path == tmp_path
        assert job.folder == tmp_path.name
        assert job.status == JobStatus.QUEUED

        active = queue.get_active_validation_job(tmp_path)
        assert active is not None
        assert active.job_id == job.job_id

    async def test_enqueue_is_idempotent(self, tmp_path: Path) -> None:
        """Re-enqueueing the same folder returns the existing job."""
        queue = JobQueue()
        first = await queue.enqueue_validation(tmp_path)
        second = await queue.enqueue_validation(tmp_path)

        assert first.job_id == second.job_id

    async def test_get_active_returns_none_when_no_job(self, tmp_path: Path) -> None:
        queue = JobQueue()
        assert queue.get_active_validation_job(tmp_path) is None


class TestRunValidation:
    """Direct invocation of JobQueue._run_validation()."""

    @pytest.fixture(autouse=True)
    def _stub_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Stub get_settings() so active_set.get_builtin_recording_validators
        does not need real env vars (RECORDING_CONFIG / OUTPUT_DIR)."""
        from unittest.mock import MagicMock

        mock_s = MagicMock()
        mock_s.recording.validators = []
        monkeypatch.setattr("app.features.validation.active_set.get_settings", lambda: mock_s)

    async def test_writes_validation_result(self, tmp_path: Path) -> None:
        """A successful run produces validation_result.json."""
        _write_quality_report(tmp_path)
        _write_meta(tmp_path, task_name="my_task")

        queue = JobQueue()
        job = await queue.enqueue_validation(tmp_path)
        await queue._run_validation(job)

        report = load_report(tmp_path)
        assert report is not None
        assert report.task_name == "my_task"
        assert report.overall_status == "pass"

    async def test_skips_when_cache_exists(self, tmp_path: Path) -> None:
        """An existing cache short-circuits execution."""
        existing = {
            "overall_status": "warn",
            "results": [],
            "task_name": "preserved",
            "executed_at": "2026-05-25T12:00:00+00:00",
        }
        (tmp_path / CACHE_FILENAME).write_text(json.dumps(existing), encoding="utf-8")

        queue = JobQueue()
        job = await queue.enqueue_validation(tmp_path)
        await queue._run_validation(job)

        # Cache is left untouched.
        report = load_report(tmp_path)
        assert report is not None
        assert report.task_name == "preserved"
        assert report.overall_status == "warn"

    async def test_fails_when_quality_report_missing(self, tmp_path: Path) -> None:
        """Without a quality report, validation must fail with a clear error."""
        queue = JobQueue()
        job = await queue.enqueue_validation(tmp_path)

        with pytest.raises(FileNotFoundError, match=r"quality_report\.json"):
            await queue._run_validation(job)

    async def test_handles_missing_recording_meta(self, tmp_path: Path) -> None:
        """A missing recording_meta.json still lets validation run (task_name=None)."""
        _write_quality_report(tmp_path)

        queue = JobQueue()
        job = await queue.enqueue_validation(tmp_path)
        await queue._run_validation(job)

        report = load_report(tmp_path)
        assert report is not None
        assert report.task_name is None

    async def test_passes_mcap_path_to_validator(self, tmp_path: Path) -> None:
        """When an MCAP file is present, ctx.mcap_path is set to it."""
        _write_quality_report(tmp_path)
        mcap_path = tmp_path / "rec_0.mcap"
        mcap_path.write_bytes(b"")

        @register_validator
        class _Capture(RecordingValidator):
            name: ClassVar[str] = "capture_mcap_path"
            seen: ClassVar[Path | None] = None

            def validate(self, ctx: ValidationContext) -> ValidationResult:
                type(self).seen = ctx.mcap_path
                return ValidationResult(status="pass", message="ok")

        queue = JobQueue()
        job = await queue.enqueue_validation(tmp_path)
        await queue._run_validation(job)

        assert _Capture.seen == mcap_path

    async def test_mcap_path_is_none_when_missing(self, tmp_path: Path) -> None:
        """No MCAP in the folder → ctx.mcap_path is None."""
        _write_quality_report(tmp_path)

        @register_validator
        class _Capture(RecordingValidator):
            name: ClassVar[str] = "capture_mcap_path_none"
            seen: ClassVar[Path | None] = Path("/sentinel")

            def validate(self, ctx: ValidationContext) -> ValidationResult:
                type(self).seen = ctx.mcap_path
                return ValidationResult(status="pass", message="ok")

        queue = JobQueue()
        job = await queue.enqueue_validation(tmp_path)
        await queue._run_validation(job)

        assert _Capture.seen is None
