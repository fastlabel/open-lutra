"""Sentinel upload destination used when no backend is selected.

Returned by :func:`get_active_destination` when ``UPLOAD_DESTINATION`` is
unset. ``configuration_error()`` always returns a non-``None`` message so
the upload feature stays disabled (the ``/api/upload/start`` endpoint
refuses to enqueue and the UI hides its affordances).

``prepare_target`` / ``upload`` raise on call. They are unreachable in
practice because every caller gates on ``configuration_error()`` first,
but they guard against programming errors that bypass that contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from app.features.upload.destinations.base import ProgressCallback, UploadResult


class DisabledDestination:
    """No-op destination returned when ``UPLOAD_DESTINATION`` is unset."""

    name = "disabled"

    def configuration_error(self) -> str | None:
        return "UPLOAD_DESTINATION is not configured"

    def prepare_target(self, recording_name: str, recording_start_ns: int) -> tuple[str, str]:  # noqa: ARG002
        raise RuntimeError("Upload destination is not configured")

    def upload(
        self,
        local_path: Path,  # noqa: ARG002
        key: str,  # noqa: ARG002
        progress: ProgressCallback,  # noqa: ARG002
    ) -> UploadResult:
        raise RuntimeError("Upload destination is not configured")
