"""Load and save `upload_state.json`.

Stored alongside `quality_report.json` / `validation_result.json` in the
recording directory.
"""

import json
import logging
from pathlib import Path

from app.features.upload.models import UploadState

logger = logging.getLogger(__name__)

CACHE_FILENAME = "upload_state.json"


def save_state(directory: Path, state: UploadState) -> None:
    """Persist the UploadState as upload_state.json."""
    path = directory / CACHE_FILENAME
    path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_state(directory: Path) -> UploadState | None:
    """Read upload_state.json if present.

    Returns None when the file is missing or unreadable (only a warning
    is logged in the latter case).
    """
    path = directory / CACHE_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return UploadState.model_validate(data)
    except (json.JSONDecodeError, ValueError, OSError) as e:
        logger.warning("Failed to read upload state: %s (%s)", path, e)
        return None
