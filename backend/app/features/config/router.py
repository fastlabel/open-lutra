"""Configuration and system information API endpoints."""

from fastapi import APIRouter

from app.features.config.mapper import to_metadata_field_responses
from app.features.config.memory_reader import read_limit_bytes, read_usage_bytes
from app.features.config.schemas import ConfigResponse, HealthResponse, MemoryInfo
from app.features.upload.service import is_upload_enabled
from app.settings import get_settings

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/health", response_model=HealthResponse, operation_id="healthCheck")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok")


@router.get("/config", response_model=ConfigResponse, operation_id="getConfig")
async def get_config() -> ConfigResponse:
    """Expose application configuration to the frontend."""
    settings = get_settings()
    return ConfigResponse(
        ros_domain_id=settings.ros_domain_id,
        robot_name=settings.robot_name,
        default_topics=settings.default_topics,
        stamp_quality=settings.stamp_quality,
        upload_enabled=is_upload_enabled(settings),
        metadata_fields=to_metadata_field_responses(settings.metadata_fields),
    )


@router.get("/system/memory", response_model=MemoryInfo, operation_id="getMemory")
async def get_memory() -> MemoryInfo:  # pragma: no cover
    """Get the memory usage of the backend process."""
    return MemoryInfo(used_bytes=read_usage_bytes(), limit_bytes=read_limit_bytes())
