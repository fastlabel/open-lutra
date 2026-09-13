"""Configuration and system information schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class MemoryInfo(BaseModel):
    """Response for GET /api/system/memory."""

    used_bytes: int
    limit_bytes: int | None


class StorageInfo(BaseModel):
    """Response for GET /api/system/storage."""

    path: str = Field(..., description="Output directory whose volume was measured")
    free_bytes: int | None = Field(
        ...,
        description=(
            "Bytes still writable by the recorder, excluding the blocks a filesystem "
            "reserves for the superuser. null when the volume cannot be inspected."
        ),
    )


class HealthResponse(BaseModel):
    """Response for GET /api/health."""

    status: str


class MetadataFieldOptionResponse(BaseModel):
    """A selectable value for a pre-registered metadata field."""

    value: str
    label: str


class MetadataFieldResponse(BaseModel):
    """A pre-registered metadata field the operator sets before recording."""

    key: str
    label: str
    type: Literal["select", "number", "text"]
    pattern: str | None
    placeholder: str | None
    options: list[MetadataFieldOptionResponse]


class ConfigResponse(BaseModel):
    """Response for GET /api/config."""

    ros_domain_id: int
    robot_name: str
    default_topics: list[str]
    stamp_quality: bool
    upload_enabled: bool
    metadata_fields: list[MetadataFieldResponse]
