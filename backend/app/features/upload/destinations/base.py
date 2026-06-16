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

        Covers every check that must pass before an upload can be enqueued
        (env vars set, key/path template parses, etc.). Drives both the
        ``/api/upload/start`` early-rejection path and the UI's "hide upload
        affordances when not configured" toggle.
        """
        ...

    def prepare_target(self, recording_name: str, recording_start_ns: int) -> tuple[str, str]:
        """Resolve the ``(destination_label, key)`` pair for this upload.

        ``destination_label`` is what gets persisted to
        ``UploadState.destination`` (bucket name for S3, mounted-dir path for
        local, container name for GCS). ``key`` is the object / path key
        within that destination, rendered from the destination's configured
        template.

        Called once per upload before transfer begins. Raises if the template
        cannot be rendered — but ``configuration_error()`` should already have
        rejected unusable templates, so this path is reserved for runtime
        inputs (e.g. ``recording_start_ns``).
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
