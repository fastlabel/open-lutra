"""API schemas for upload endpoints.

Domain models live in ``models.py``. This module only wraps them for HTTP responses.
"""

from pydantic import BaseModel, Field

from app.features.upload.models import UploadState


class UploadResponse(BaseModel):
    """Response for ``GET /api/upload`` and ``POST /api/upload/start``.

    ``status`` reflects the current upload phase as observed by the service:

    * ``uploaded`` — persisted ``upload_state.json`` carries that status.
    * ``uploading`` — persisted state with that status, or an active job in
      the queue.
    * ``failed`` — persisted state with that status, the last job ended in
      failure, or the start path rejected the request (e.g. destination
      misconfigured).
    * ``idle`` — persisted state explicitly marked as idle.
    * ``not_found`` — no persisted state and no active job.
    """

    status: str = Field(..., pattern=r"^(idle|uploading|uploaded|failed|not_found)$")
    state: UploadState | None
    error: str | None


class BulkUploadRequest(BaseModel):
    """Request body for ``POST /api/upload/start-bulk``."""

    folders: list[str] = Field(..., description="Recording folder names to enqueue for upload")


class BulkUploadResultItem(BaseModel):
    """Per-folder outcome inside a bulk-upload response.

    * ``uploading`` — the folder was enqueued, or an upload was already in flight
      for it (the existing job is returned per the queue's dedup guard).
    * ``failed`` — the folder could not be enqueued (path traversal, missing
      directory). The reason is in ``error``.
    """

    folder: str
    status: str = Field(..., pattern=r"^(uploading|failed)$")
    error: str | None


class BulkUploadResponse(BaseModel):
    """Response for ``POST /api/upload/start-bulk``.

    Best-effort: each requested folder is reported in ``results`` regardless of
    whether the enqueue succeeded. Order matches the request's ``folders`` list.

    Global configuration errors (destination not set / key template invalid)
    are surfaced as HTTP 400 by the service rather than as per-folder failures,
    since they would otherwise be repeated identically across every entry.
    """

    results: list[BulkUploadResultItem]
