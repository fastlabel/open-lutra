"""API facade for the validation feature.

Delegates actual execution to the JobQueue in `app/features/jobs/`.
This module only assembles HTTP responses, mirroring `QualityAnalyzer`.

Benefits of using the job queue:
  - Active jobs are visible in the StatusBar.
  - Duplicate runs on the same folder are prevented.
  - A single worker serializes MCAP I/O.
"""

import logging
from pathlib import Path

from app.features.analysis.mcap_analyzer import load_report as load_quality_report
from app.features.jobs.models import JobStatus
from app.features.jobs.service import get_job_queue
from app.features.validation.cache import load_report
from app.features.validation.schemas import ValidationResponse

logger = logging.getLogger(__name__)


class ValidationService:
    """Validation API facade. Execution is delegated to the job queue."""

    async def get(self, target: Path) -> ValidationResponse:
        """Return the validation report (no side effects).

        Returns the cached report if present; otherwise returns the current
        status (analyzing / error / not_found).
        """
        report = load_report(target)
        if report:
            return ValidationResponse(status="ready", report=report, error=None)

        queue = get_job_queue()
        active = queue.get_active_validation_job(target)
        if active is not None and active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return ValidationResponse(status="analyzing", report=None, error=None)

        if active is not None and active.status == JobStatus.FAILED:
            return ValidationResponse(
                status="error",
                report=None,
                error=active.error or "Validation failed",
            )

        return ValidationResponse(status="not_found", report=None, error=None)

    async def start(self, target: Path) -> ValidationResponse:
        """Trigger a validation run (idempotent: returns the existing job's status if any)."""
        report = load_report(target)
        if report:
            return ValidationResponse(status="ready", report=report, error=None)

        queue = get_job_queue()
        active = queue.get_active_validation_job(target)
        if active is not None and active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return ValidationResponse(status="analyzing", report=None, error=None)

        # Validation requires the quality report to be available.
        if load_quality_report(target) is None:
            return ValidationResponse(
                status="not_found",
                report=None,
                error="Quality report not available (run quality analysis first)",
            )

        await queue.enqueue_validation(target)
        return ValidationResponse(status="analyzing", report=None, error=None)

    async def schedule(self, target: Path) -> None:
        """Enqueue a validation job (used by the post-recording auto-chain).

        Does nothing if a report is already cached or a job is already queued.
        """
        if load_report(target) is not None:
            return

        queue = get_job_queue()
        active = queue.get_active_validation_job(target)
        if active is not None and active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return

        await queue.enqueue_validation(target)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_validation_service_singleton = ValidationService()


def get_validation_service() -> ValidationService:
    return _validation_service_singleton
