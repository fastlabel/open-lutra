"""System update API endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.dependencies import RecorderDep
from app.features.system_update.agent_client import (
    AgentUnavailableError,
    NoPendingUpdateError,
    apply_update,
    fetch_status,
)
from app.features.system_update.schemas import SystemUpdateStatus
from app.settings import get_settings

router = APIRouter(prefix="/api/system/update", tags=["system"])


@router.get("", response_model=SystemUpdateStatus, operation_id="getSystemUpdate")
async def get_system_update() -> SystemUpdateStatus:
    """Get whether a software update is waiting to be applied."""
    return await fetch_status(get_settings().update_agent_url)


@router.post(
    "/apply",
    response_model=SystemUpdateStatus,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="applySystemUpdate",
    responses={
        409: {"description": "Recording in progress, or no pending update"},
        503: {"description": "Update agent unavailable"},
    },
)
async def apply_system_update(recorder: RecorderDep) -> SystemUpdateStatus:
    """Apply the pending software update. The application restarts shortly after."""
    if recorder.is_recording:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Stop recording before updating")
    try:
        return await apply_update(get_settings().update_agent_url)
    except NoPendingUpdateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No pending update") from e
    except AgentUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e
