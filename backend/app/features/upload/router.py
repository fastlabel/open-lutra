"""Upload API endpoints."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends

from app.dependencies import require_dir
from app.features.upload.schemas import UploadResponse
from app.features.upload.service import get_upload_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.get("", response_model=UploadResponse, operation_id="getUpload")
async def get_upload(  # pragma: no cover
    target: Path = Depends(require_dir),
) -> UploadResponse:
    """Return the current upload state (no side effects).

    Trigger an upload via ``POST /api/upload/start``.
    """
    return await get_upload_service().get(target)


@router.post("/start", response_model=UploadResponse, operation_id="startUpload")
async def start_upload(  # pragma: no cover
    target: Path = Depends(require_dir),
) -> UploadResponse:
    """Trigger an upload.

    Idempotent: returns the existing job's status when one is already
    running. When no job is active this always overwrites the previously
    uploaded object (no skip-if-cached, per issue #6).
    """
    return await get_upload_service().start(target)
