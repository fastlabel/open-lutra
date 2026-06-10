"""S3 object key template rendering.

The key template comes from the `S3_KEY_TEMPLATE` env var and supports the
following placeholders:

    {task_name}        — from recording_meta.json
    {recording_name}   — the recording folder name
    {yyyymmddhhmmss}   — recording start time (UTC), 14-digit string

Template validation rejects unknown placeholders and unbalanced braces so
that misconfiguration surfaces as a clear upload-time error rather than
silently producing a corrupt S3 key.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
_ALLOWED_PLACEHOLDERS = frozenset({"task_name", "recording_name", "yyyymmddhhmmss"})


class KeyTemplateError(ValueError):
    """Raised when the template is malformed or references unknown placeholders."""


def validate_template(template: str) -> None:
    """Verify that every placeholder is known and braces are balanced.

    Raises KeyTemplateError on any issue.
    """
    if template.count("{") != template.count("}"):
        raise KeyTemplateError(f"Unbalanced braces in S3 key template: {template!r}")

    for match in _PLACEHOLDER_RE.finditer(template):
        name = match.group(1)
        if name not in _ALLOWED_PLACEHOLDERS:
            raise KeyTemplateError(
                f"Unknown placeholder {{{name}}} in S3 key template. "
                f"Allowed: {sorted(_ALLOWED_PLACEHOLDERS)}"
            )


def render_key(
    template: str,
    *,
    task_name: str,
    recording_name: str,
    recording_start_ns: int,
) -> str:
    """Substitute placeholders into the template.

    `recording_start_ns` is interpreted as nanoseconds since the Unix epoch
    (the value stored in `metadata.yaml` by `ros2 bag record`). It is rendered
    as a 14-digit UTC timestamp.

    Raises KeyTemplateError if validation fails.
    """
    validate_template(template)

    dt = datetime.fromtimestamp(recording_start_ns / 1_000_000_000, tz=timezone.utc)
    yyyymmddhhmmss = dt.strftime("%Y%m%d%H%M%S")

    return template.format(
        task_name=task_name,
        recording_name=recording_name,
        yyyymmddhhmmss=yyyymmddhhmmss,
    )
