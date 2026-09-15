"""Request/response schemas for the jobs API."""

from typing import Literal

from pydantic import BaseModel, Field

from app.features.jobs.models import Job, JobProgress


class JobProgressSchema(BaseModel):
    """API schema for job progress."""

    step: str
    step_label: str
    current: int
    total: int

    @classmethod
    def from_progress(cls, progress: JobProgress) -> "JobProgressSchema":
        return cls(
            step=progress.step,
            step_label=progress.step_label,
            current=progress.current,
            total=progress.total,
        )


class JobSchema(BaseModel):
    """API schema for a job."""

    job_id: str
    type: str = Field(..., description="Job type (media / quality / timeline / validation / lerobot_export / upload)")
    folder: str
    status: str = Field(..., description="Job status (queued / running / completed / failed)")
    progress: JobProgressSchema
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

    @classmethod
    def from_job(cls, job: Job) -> "JobSchema":
        return cls(
            job_id=job.job_id,
            type=job.type.value,
            folder=job.folder,
            status=job.status.value,
            progress=JobProgressSchema.from_progress(job.progress),
            error=job.error,
            created_at=job.created_at.isoformat(),
            started_at=job.started_at.isoformat() if job.started_at else None,
            finished_at=job.finished_at.isoformat() if job.finished_at else None,
        )


class JobsResponse(BaseModel):
    """Response for GET /api/jobs."""

    jobs: list[JobSchema]


# ---------------------------------------------------------------------------
# SSE events (GET /api/jobs/stream)
# ---------------------------------------------------------------------------


class QueueSnapshotData(BaseModel):
    """Data payload for the `queue_snapshot` event."""

    jobs: list[JobSchema]


class QueueSnapshotEvent(BaseModel):
    """Current queue snapshot sent immediately after subscription starts."""

    event: Literal["queue_snapshot"]
    data: QueueSnapshotData


class JobChangeEvent(BaseModel):
    """Status change event for an individual job."""

    event: Literal["job_added", "job_started", "job_progress", "job_completed", "job_failed"]
    data: JobSchema


# Event type handled by Queue / SSE (tagged union)
JobEvent = QueueSnapshotEvent | JobChangeEvent
