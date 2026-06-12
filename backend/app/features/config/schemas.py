"""Configuration and system information schemas."""

from pydantic import BaseModel


class MemoryInfo(BaseModel):
    """Response for GET /api/system/memory."""

    used_bytes: int
    limit_bytes: int | None


class HealthResponse(BaseModel):
    """Response for GET /api/health."""

    status: str


class ConfigResponse(BaseModel):
    """Response for GET /api/config."""

    ros_domain_id: int
    robot_name: str
    default_topics: list[str]
    stamp_quality: bool
    upload_enabled: bool
