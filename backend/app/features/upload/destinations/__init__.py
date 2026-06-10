"""Pluggable upload destinations.

Public entry points re-exported here so the rest of the codebase imports
from ``app.features.upload.destinations`` and never reaches into specific
destination modules.
"""

from app.features.upload.destinations.base import (
    ProgressCallback,
    UploadDestination,
    UploadResult,
)
from app.features.upload.destinations.registry import get_active_destination

__all__ = [
    "ProgressCallback",
    "UploadDestination",
    "UploadResult",
    "get_active_destination",
]
