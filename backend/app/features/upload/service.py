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

from fastapi import HTTPException, status

from app.features.jobs.models import JobStatus
from app.features.jobs.service import get_job_queue
from app.features.upload.cache import load_state
from app.features.upload.destinations import get_active_destination
from app.features.upload.schemas import (
    BulkUploadResponse,
    BulkUploadResultItem,
    UploadResponse,
)
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _upload_availability_error(settings: Settings) -> str | None:
    """Return why the upload feature is not usable, or ``None`` when fully configured.

    Powers both ``UploadService.start()``'s early-rejection path and the
    ``/api/config`` ``upload_enabled`` flag. The destination owns every
    check (env vars set, template parses, etc.) — see
    :meth:`UploadDestination.configuration_error`.
    """
    return get_active_destination(settings).configuration_error()


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
        queue): anything the destination's
        :meth:`UploadDestination.configuration_error` flags (missing env
        vars, malformed key/path template, etc.).
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

    async def start_bulk(self, folder_names: list[str]) -> BulkUploadResponse:
        """Enqueue uploads for multiple recordings in one call.

        Best-effort: per-folder enqueue errors (path traversal, missing
        directory) are reported in the response without aborting the rest.
        Order in ``results`` matches the request's ``folder_names``.

        Global configuration errors (destination not set / key template
        invalid) raise HTTP 400 — they would be identical for every folder,
        so a single rejection is clearer than N copies of the same message.

        The queue's per-folder dedup applies as in :meth:`start`: a folder
        with an active upload is reported as ``uploading`` without being
        re-enqueued.
        """
        settings = get_settings()
        availability_err = _upload_availability_error(settings)
        if availability_err is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=availability_err)

        output_dir = settings.output_dir.resolve()
        queue = get_job_queue()
        results: list[BulkUploadResultItem] = []

        for name in folder_names:
            target = (output_dir / name).resolve()
            if not target.is_relative_to(output_dir):
                results.append(BulkUploadResultItem(folder=name, status="failed", error="Invalid path"))
                continue
            if not target.is_dir():
                results.append(BulkUploadResultItem(folder=name, status="failed", error="Folder not found"))
                continue

            active = queue.get_active_upload_job(target)
            if active is None or active.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                await queue.enqueue_upload(target)
            results.append(BulkUploadResultItem(folder=name, status="uploading", error=None))

        return BulkUploadResponse(results=results)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_upload_service_singleton = UploadService()


def get_upload_service() -> UploadService:
    """Return the global UploadService instance."""
    return _upload_service_singleton
