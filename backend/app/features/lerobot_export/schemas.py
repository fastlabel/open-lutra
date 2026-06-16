"""Request/response schemas for the LeRobot export API."""

from pydantic import BaseModel, Field


class LeRobotConfigResponse(BaseModel):
    """The active robot's LeRobot export mapping summary (for the export dialog)."""

    configured: bool = Field(..., description="Whether the active robot config declares a lerobot_export mapping")
    robot_type: str | None = Field(..., description="Robot type from the mapping (null when not configured)")
    cameras: list[str] = Field(..., description="Camera names produced by the mapping (empty when not configured)")


class ExportRequest(BaseModel):
    """Request body for POST /api/lerobot/export."""

    folders: list[str] = Field(..., description="Recording folder names; each becomes one episode")
    output_name: str = Field(..., description="Dataset directory name under _lerobot_exports/")


class ExportResponse(BaseModel):
    """Response for POST /api/lerobot/export."""

    job_id: str
    output_name: str
    status: str = Field(..., description="Job status (queued / running / completed / failed)")
