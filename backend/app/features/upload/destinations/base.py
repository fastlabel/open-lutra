"""Protocol shared by all upload destinations.

Concrete destinations (S3 today; GCS / local-server in the future)
implement :class:`UploadDestination`. The service layer and the job queue
program against this protocol only and never import a specific
destination module — selection is the registry's job
(:mod:`app.features.upload.destinations.registry`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

ProgressCallback = Callable[[int], None]
"""Boto3-shaped progress callback.

Invoked with the byte-delta transferred since the last call; summing the
deltas yields total bytes uploaded so far.
"""


@dataclass(frozen=True)
class UploadResult:
    """Outcome of a successful upload."""

    size_bytes: int
    etag: str | None
    """Destination-specific result identifier (S3 ETag, GCS generation,
    local hash). ``None`` when the destination does not return one."""


@runtime_checkable
class UploadDestination(Protocol):
    """Pluggable upload destination."""

    name: str
    """Destination identifier — ``"s3"``, ``"gcs"``, ``"local"``."""

    def configuration_error(self) -> str | None:
        """Return a human-readable error if the destination is not usable, else ``None``.

        Drives both the ``/api/upload/start`` early-rejection check and the
        UI's "hide upload affordances when not configured" toggle.
        """
        ...

    def upload(
        self,
        local_path: Path,
        key: str,
        progress: ProgressCallback,
    ) -> UploadResult:
        """Upload ``local_path`` to ``key`` on this destination.

        Blocks until the upload completes. ``progress`` is invoked with
        byte-delta values during transfer. Raises on failure — the caller
        is responsible for status-file bookkeeping.
        """
        ...
