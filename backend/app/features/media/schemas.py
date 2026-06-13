"""MP4 video API schemas."""

from pydantic import BaseModel, Field


class VideoProgress(BaseModel):
    """Video generation progress info."""

    step: str = Field(..., description="Current step (classify/read/mp4/telemetry)")
    step_label: str = Field(..., description="Human-readable label for the step")
    current: int = Field(..., description="Current progress (camera index for mp4)")
    total: int = Field(..., description="Total count")


class VideoResponse(BaseModel):
    """Response for GET /api/media/video."""

    status: str = Field(..., pattern=r"^(ready|generating|not_generated|error)$")
    videos: list[str]
    progress: VideoProgress | None
    error: str | None
    job_id: str | None = Field(
        ..., description="ID of the in-flight generation job (subscribe to progress via SSE /api/jobs/stream)"
    )
