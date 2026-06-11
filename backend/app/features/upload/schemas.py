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
