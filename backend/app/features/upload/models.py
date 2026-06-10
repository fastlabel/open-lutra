"""Domain models for the upload feature.

`UploadState` is persisted as `upload_state.json` inside each recording
folder, mirroring how validation persists `validation_result.json`.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

UploadStatus = Literal["idle", "uploading", "uploaded", "failed"]


class UploadState(BaseModel):
    """Persisted upload state for one recording.

    Fields are required (no defaults) so JSON written by older versions
    surfaces as a parse error instead of silently defaulting to zero values.
    """

    status: UploadStatus
    s3_bucket: str | None
    s3_key: str | None
    etag: str | None
    size_bytes: int | None
    bytes_transferred: int
    uploaded_at: datetime | None
    error: str | None
