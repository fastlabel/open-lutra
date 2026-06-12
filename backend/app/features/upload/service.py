"""API facade for the upload feature.

Delegates actual execution to the JobQueue in ``app/features/jobs/``.
This module only assembles HTTP responses, mirroring ``ValidationService``.

Benefits of using the job queue:

* Active uploads are visible in the StatusBar.
* Duplicate uploads on the same folder are prevented by the queue's
  per-folder dedup.
* A single worker serializes upload I/O.
"""

import logging
from pathlib import Path

from app.features.jobs.models import JobStatus
from app.features.jobs.service import get_job_queue
from app.features.upload.cache import load_state
from app.features.upload.destinations import get_active_destination
from app.features.upload.key_template import validate_template
from app.features.upload.schemas import UploadResponse
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _upload_availability_error(settings: Settings) -> str | None:
    """Return why the upload feature is not usable, or ``None`` when fully configured.

    Powers both ``UploadService.start()``'s early-rejection path and the
    ``/api/config`` ``upload_enabled`` flag.
    """
    destination = get_active_destination(settings)
    err = destination.configuration_error()
    if err is not None:
        return err
    # configuration_error() guarantees the template is set; assert for the type checker.
    assert settings.s3_key_template is not None
    try:
        validate_template(settings.s3_key_template)
    except ValueError as e:
        return str(e)
    return None


def is_upload_enabled(settings: Settings) -> bool:
    """Whether the upload feature is fully usable.

    Drives the UI's "hide upload affordances when not configured" toggle
    via ``/api/config``. True only when the destination is configured
    and the key template parses without error.
    """
    return _upload_availability_error(settings) is None


class UploadService:
    """Upload API facade. Execution is delegated to the job queue."""

    async def get(self, target: Path) -> UploadResponse:
        """Return the current upload state (no side effects).

        Resolution order:

        1. Persisted ``upload_state.json`` if present — its status (uploaded /
           uploading / failed / idle) is reported directly.
        2. Active job in the queue: ``uploading`` while queued/running,
           ``failed`` when the last job ended in failure.
        3. ``not_found`` otherwise.
        """
        state = load_state(target)
        if state is not None:
            return UploadResponse(status=state.status, state=state, error=state.error)

        queue = get_job_queue()
        active = queue.get_active_upload_job(target)
        if active is not None and active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return UploadResponse(status="uploading", state=None, error=None)
        if active is not None and active.status == JobStatus.FAILED:
            return UploadResponse(
                status="failed",
                state=None,
                error=active.error or "Upload failed",
            )

        return UploadResponse(status="not_found", state=None, error=None)

    async def start(self, target: Path) -> UploadResponse:
        """Trigger an upload.

        Always overwrites the previously uploaded object (per issue #6 — no
        skip-if-cached). If a job is already active for ``target``, returns
        the existing job's status without enqueueing a second one.

        Early rejections (returns ``status="failed"`` without touching the
        queue):

        * Destination is not configured (S3_BUCKET / S3_KEY_TEMPLATE unset).
        * Key template syntax is invalid (unknown placeholder, unbalanced
          braces).
        """
        err = _upload_availability_error(get_settings())
        if err is not None:
            return UploadResponse(status="failed", state=None, error=err)

        queue = get_job_queue()
        active = queue.get_active_upload_job(target)
        if active is not None and active.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            return UploadResponse(status="uploading", state=load_state(target), error=None)

        await queue.enqueue_upload(target)
        return UploadResponse(status="uploading", state=load_state(target), error=None)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_upload_service_singleton = UploadService()


def get_upload_service() -> UploadService:
    """Return the global UploadService instance."""
    return _upload_service_singleton
