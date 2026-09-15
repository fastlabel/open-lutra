"""API facade for quality analysis.

The actual analysis runs on the JobQueue in `app/features/jobs/`.
This module is a thin layer that only assembles API responses.

Benefits of the job queue integration:
  - Surface running tasks in the StatusBar
  - Prevent duplicate execution for the same folder
  - Reduce MCAP I/O contention via a single worker
"""

import logging
from pathlib import Path

from app.features.analysis.mcap_analyzer import load_report
from app.features.analysis.schemas import QualityResponse
from app.features.jobs.models import JobStatus
from app.features.jobs.service import get_job_queue

logger = logging.getLogger(__name__)


class QualityAnalyzer:
    """API facade for quality analysis. Delegates execution to the job queue."""

    async def get(self, target: Path) -> QualityResponse:
        """Get the quality report (no side effects).

        Returns the cached report if available, otherwise returns only the
        current status.
        """
        report = load_report(target)
        if report:
            return QualityResponse(status="ready", report=report, error=None)

        queue = get_job_queue()
        active = queue.get_active_quality_job(target)
        if active is not None and active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return QualityResponse(status="analyzing", report=None, error=None)

        if active is not None and active.status == JobStatus.FAILED:
            return QualityResponse(status="error", report=None, error=active.error or "Quality analysis failed")

        return QualityResponse(status="not_found", report=None, error=None)

    async def start(self, target: Path) -> QualityResponse:
        """Start quality analysis (idempotent: returns the existing job status if already running)."""
        report = load_report(target)
        if report:
            return QualityResponse(status="ready", report=report, error=None)

        queue = get_job_queue()
        active = queue.get_active_quality_job(target)
        if active is not None and active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return QualityResponse(status="analyzing", report=None, error=None)

        if not list(target.glob("*.mcap")):
            return QualityResponse(status="not_found", report=None, error="MCAP file not found")

        await queue.enqueue_quality(target)
        return QualityResponse(status="analyzing", report=None, error=None)

    async def schedule(self, target: Path) -> None:
        """Enqueue quality analysis (used for automatic analysis after recording stops).

        Does nothing if already cached or already enqueued.
        """
        if load_report(target) is not None:
            return
        if not list(target.glob("*.mcap")):
            return

        queue = get_job_queue()
        await queue.enqueue_quality(target)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_quality_analyzer_singleton = QualityAnalyzer()


def get_quality_analyzer() -> QualityAnalyzer:
    return _quality_analyzer_singleton
