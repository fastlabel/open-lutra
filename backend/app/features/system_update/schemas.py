"""System update schemas."""

from pydantic import BaseModel


class SystemUpdateStatus(BaseModel):
    """Response for GET /api/system/update and POST /api/system/update/apply.

    `enabled` is false when no update agent is configured; the UI hides its
    update affordances in that case.
    """

    enabled: bool
    available: bool
    applying: bool
