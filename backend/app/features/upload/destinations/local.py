"""Local-filesystem upload destination.

Targets a directory that the operator has mounted into the backend
container — typically an NFS or SMB share bind-mounted at
``LOCAL_UPLOAD_DIR``. The destination key is rendered the same way as for
S3 (see :mod:`app.features.upload.key_template`) and resolves to a path
under that directory.

The copy is a single :func:`shutil.copyfile` — no temp-and-rename, no
per-chunk progress. The progress callback fires once at completion so the
``upload_state.json`` ``bytes_transferred`` field and the StatusBar
percent reflect the final size.
"""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from app.features.upload.destinations.base import ProgressCallback, UploadResult
from app.features.upload.key_template import KeyTemplateError, render_key, validate_template

if TYPE_CHECKING:
    from pathlib import Path

    from app.settings import Settings


class LocalDestination:
    """Upload to a directory on the backend container's filesystem."""

    name = "local"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def configuration_error(self) -> str | None:
        directory = self._settings.local_upload_dir
        if directory is None:
            return "LOCAL_UPLOAD_DIR is not configured"
        if not self._settings.local_upload_path_template:
            return "LOCAL_UPLOAD_PATH_TEMPLATE is not configured"
        if not directory.is_dir():
            return f"LOCAL_UPLOAD_DIR does not exist: {directory}"
        if not os.access(directory, os.W_OK):
            return f"LOCAL_UPLOAD_DIR is not writable: {directory}"
        try:
            validate_template(self._settings.local_upload_path_template)
        except KeyTemplateError as e:
            return str(e)
        return None

    def prepare_target(self, recording_name: str, recording_start_ns: int) -> tuple[str, str]:
        directory = self._settings.local_upload_dir
        template = self._settings.local_upload_path_template
        if directory is None or template is None:
            # Defensive: configuration_error() should have rejected this upload
            # before prepare_target() is reached.
            raise RuntimeError("Local destination is not configured")
        key = render_key(
            template,
            recording_name=recording_name,
            recording_start_ns=recording_start_ns,
        )
        return str(directory), key

    def upload(
        self,
        local_path: Path,
        key: str,
        progress: ProgressCallback,
    ) -> UploadResult:
        directory = self._settings.local_upload_dir
        if directory is None:
            # Defensive: the caller is expected to gate on
            # configuration_error(); this guards against programming errors
            # that bypass that contract.
            raise RuntimeError("LOCAL_UPLOAD_DIR is not configured")

        target = directory / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, target)
        size = target.stat().st_size
        progress(size)
        return UploadResult(size_bytes=size, etag=None)
