"""Pure mapping helpers for the config API."""

from pathlib import Path

from app.features.config.schemas import (
    MetadataFieldOptionResponse,
    MetadataFieldResponse,
    StorageInfo,
)
from app.settings import MetadataField
from app.shared.disk import DiskUsage


def to_metadata_field_responses(fields: list[MetadataField]) -> list[MetadataFieldResponse]:
    """Convert master metadata fields to API responses.

    Each option's display label falls back to its value when omitted so the
    frontend always has a label to render.
    """
    return [
        MetadataFieldResponse(
            key=field.key,
            label=field.label,
            type=field.type,
            pattern=field.pattern,
            placeholder=field.placeholder,
            options=[
                MetadataFieldOptionResponse(value=option.value, label=option.label or option.value)
                for option in field.options
            ],
        )
        for field in fields
    ]


def to_storage_info(path: Path, usage: DiskUsage | None) -> StorageInfo:
    """Convert the output volume's capacity to an API response.

    An uninspectable volume still reports its path, with the byte counts left
    null so the frontend can show the path it failed on.
    """
    return StorageInfo(
        path=str(path),
        total_bytes=usage.total_bytes if usage else None,
        used_bytes=usage.used_bytes if usage else None,
        free_bytes=usage.free_bytes if usage else None,
    )
