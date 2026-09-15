"""Internal domain models for the recording feature.

Exception classes and value objects.
Kept separate from the Pydantic schemas used for API responses (schemas.py).
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class RecorderError(Exception):
    """Base exception for recording errors."""


class AlreadyRecordingError(RecorderError):
    """Raised when start is called while a recording is already in progress."""


class NotRecordingError(RecorderError):
    """Raised when stop is called while no recording is in progress."""


@dataclass(frozen=True)
class StopResult:
    start_time: datetime
    end_time: datetime
    output_path: Path


@dataclass(frozen=True)
class RecorderStatus:
    is_recording: bool
    output_path: Path | None = None
    start_time: datetime | None = None
    elapsed_sec: float = 0.0
