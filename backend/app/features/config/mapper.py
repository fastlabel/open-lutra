"""Pure mapping helpers for the config API."""

from pathlib import Path

from app.features.config.schemas import (
    MetadataFieldOptionResponse,
    MetadataFieldResponse,
    StorageInfo,
)
from app.settings import MetadataField


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


def to_storage_info(path: Path, free_bytes: int | None) -> StorageInfo:
    """Convert the output volume's free space to an API response.

    An uninspectable volume still reports its path, with the byte count left
    null so the frontend can name the volume it failed on.
    """
    return StorageInfo(path=str(path), free_bytes=free_bytes)
