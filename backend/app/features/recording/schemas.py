"""Recording API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class RecordingStartRequest(BaseModel):
    """Recording start request."""

    topics: list[str] | None = Field(
        default=None,
        description="Topics to record. If None, the default configuration is used.",
    )
    task_name: str | None = Field(
        default=None,
        description="Task name. When provided, used as a prefix for the recording directory name.",
    )
    metadata: dict[str, str] | None = Field(
        default=None,
        description="Pre-registered metadata (key -> value) persisted into recording_meta.json.",
    )


class RecordingStartResponse(BaseModel):
    """Recording start response."""

    output_path: str
    start_time: datetime


class RecordingStopResponse(BaseModel):
    """Recording stop response."""

    output_path: str
    start_time: datetime
    end_time: datetime
    duration_sec: float


class RecordingStatus(BaseModel):
    """Current recording status."""

    is_recording: bool
    output_path: str | None
    start_time: datetime | None
    elapsed_sec: float
