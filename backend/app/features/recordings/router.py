"""API endpoints for recording directory operations."""

import logging
import shutil

from fastapi import APIRouter, HTTPException, status

from app.dependencies import require_dir, resolve_safe_path
from app.features.recordings.meta import update_recording_meta
from app.features.recordings.scanner import collect_recent_task_names, scan_output_dir
from app.features.recordings.schemas import (
    DeleteRequest,
    DeleteResponse,
    FilesResponse,
    RenameRequest,
    RenameResponse,
    TaskNamesResponse,
    UpdateMetaRequest,
    UpdateMetaResponse,
)
from app.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


@router.get("", response_model=FilesResponse, operation_id="getRecordings")
def list_recordings() -> FilesResponse:  # pragma: no cover
    """List recording folders directly under the output directory."""
    settings = get_settings()
    output_dir = settings.output_dir

    if not output_dir.is_dir():
        return FilesResponse(output_dir=str(output_dir), entries=[])

    return FilesResponse(output_dir=str(output_dir), entries=scan_output_dir(output_dir))


@router.get("/task-names", response_model=TaskNamesResponse, operation_id="getRecordingTaskNames")
def list_task_names() -> TaskNamesResponse:  # pragma: no cover
    """Return previously-used task_name values, deduped and most-recent first.

    Powers the autocomplete on the recording-start form.
    """
    settings = get_settings()
    return TaskNamesResponse(task_names=collect_recent_task_names(settings.output_dir))


@router.put("/rename", response_model=RenameResponse, operation_id="renameRecording")
def rename_recording(req: RenameRequest) -> RenameResponse:  # pragma: no cover
    """Rename the recording folder and its mcap files."""
    old_dir = require_dir(resolve_safe_path(path=req.old_name))

    new_dir = old_dir.parent / req.new_name
    if new_dir.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A folder with that name already exists")

    try:
        # Rename mcap files ({old_name}_0.mcap -> {new_name}_0.mcap)
        for mcap in old_dir.glob("*.mcap"):
            suffix = mcap.name.removeprefix(req.old_name)
            mcap.rename(old_dir / f"{req.new_name}{suffix}")

        # Update file references inside metadata.yaml.
        meta = old_dir / "metadata.yaml"
        if meta.exists():
            text = meta.read_text(encoding="utf-8")
            text = text.replace(req.old_name, req.new_name)
            meta.write_text(text, encoding="utf-8")

        # Rename the folder itself.
        old_dir.rename(new_dir)
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Rename failed: {e}") from e

    return RenameResponse(name=req.new_name)


@router.patch(
    "/{name}",
    response_model=UpdateMetaResponse,
    operation_id="updateRecordingMeta",
)
def update_recording_meta_endpoint(name: str, req: UpdateMetaRequest) -> UpdateMetaResponse:  # pragma: no cover
    """Partially update task_name / tags in recording_meta.json.

    Creates the file on PATCH even for older recording folders that do
    not yet have one.
    """
    target = require_dir(resolve_safe_path(path=name))
    updated = update_recording_meta(target, task_name=req.task_name, tags=req.tags, metadata=req.metadata)
    return UpdateMetaResponse(
        task_name=updated.task_name,
        recording_config_name=updated.recording_config_name,
        tags=updated.tags,
        metadata=updated.metadata,
    )


@router.delete("", response_model=DeleteResponse, operation_id="deleteRecordings")
def delete_recordings(req: DeleteRequest) -> DeleteResponse:  # pragma: no cover
    """Delete multiple recording folders in one call."""
    deleted: list[str] = []

    for folder in req.folders:
        target = resolve_safe_path(path=folder)
        if not target.is_dir():
            continue

        try:
            shutil.rmtree(target)
            deleted.append(folder)
        except OSError as e:
            logger.error("Failed to delete folder: %s - %s", folder, e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Delete failed: {folder} ({e})",
            ) from e

    return DeleteResponse(deleted=deleted)
