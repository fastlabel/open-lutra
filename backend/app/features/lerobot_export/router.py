"""API endpoints for exporting recordings to LeRobot datasets."""

import logging
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.features.jobs.service import get_job_queue
from app.features.lerobot_export.config_loader import has_active_config, load_active_config
from app.features.lerobot_export.schemas import (
    ExportRequest,
    ExportResponse,
    LeRobotConfigResponse,
)
from app.features.lerobot_export.validation import StructureMismatchError, validate_recordings
from app.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lerobot", tags=["lerobot"])


@router.get("/config", response_model=LeRobotConfigResponse, operation_id="getLeRobotConfig")
def get_config() -> LeRobotConfigResponse:  # pragma: no cover
    """Return the active robot's LeRobot export mapping summary for the dialog."""
    return build_config_info()


@router.post("/export", response_model=ExportResponse, operation_id="startLeRobotExport")
async def start_export(req: ExportRequest) -> ExportResponse:  # pragma: no cover
    """Validate the selection and enqueue a LeRobot export job."""
    output_dir = get_settings().output_dir
    try:
        source_dirs = resolve_source_dirs(req.folders, output_dir)
        dataset_dir = resolve_dataset_dir(req.output_name, output_dir)
        config = load_active_config()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    if dataset_dir.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An export with that name already exists")

    # Reject up front when a recording's metadata.yaml does not match the config.
    try:
        validate_recordings(source_dirs, config)
    except StructureMismatchError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    queue = get_job_queue()
    job = await queue.enqueue_lerobot_export(source_dirs=source_dirs, output_dir=dataset_dir)
    return ExportResponse(job_id=job.job_id, output_name=req.output_name, status=job.status.value)


# ---------------------------------------------------------------------------
# Pure helpers (tested directly; endpoints above are HTTP glue)
# ---------------------------------------------------------------------------


def build_config_info() -> LeRobotConfigResponse:
    """Summarize the active robot's export mapping (configured flag + cameras)."""
    if not has_active_config():
        return LeRobotConfigResponse(configured=False, robot_type=None, cameras=[])
    config = load_active_config()
    return LeRobotConfigResponse(
        configured=True,
        robot_type=config.robot_type,
        cameras=list(config.images.keys()),
    )


def resolve_source_dirs(folders: list[str], output_dir: Path) -> list[Path]:
    """Resolve recording folder names to safe directories under output_dir.

    Raises:
        ValueError: If the selection is empty, escapes output_dir, or is missing.
    """
    if not folders:
        raise ValueError("No recordings selected")
    base = output_dir.resolve()
    resolved: list[Path] = []
    for folder in folders:
        target = (base / folder).resolve()
        if not target.is_relative_to(base):
            raise ValueError(f"Invalid folder path: {folder}")
        if not target.is_dir():
            raise ValueError(f"Recording folder not found: {folder}")
        resolved.append(target)
    return resolved


# Dataset names must start with an alphanumeric and contain only [A-Za-z0-9._-].
# This rejects "", path separators, "..", and leading "." / "." itself — a leading
# dot collides with the in-progress temp-dir convention (`.<name>.*.tmp`), and "."
# collapses onto the exports root (Path / "." == exports_root), letting a rename
# clobber it.
_OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def resolve_dataset_dir(output_name: str, output_dir: Path) -> Path:
    """Resolve a safe dataset directory under _lerobot_exports/.

    Raises:
        ValueError: If the name is empty or not an allowed dataset name.
    """
    from app.features.lerobot_export.exports import exports_root

    name = output_name.strip()
    if not _OUTPUT_NAME_RE.match(name):
        raise ValueError(
            "Export name must start with a letter or digit and use only letters, digits, '.', '_', '-'"
        )
    return exports_root(output_dir) / name
