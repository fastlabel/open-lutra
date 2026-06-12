"""Load the LeRobot export mapping from the active recording config.

The mapping is declared under the `lerobot_export:` key of the recording YAML
config (`config/<recording>.yaml`, selected via `RECORDING_CONFIG`) — not in a
separate file — so a recording's config and its export layout stay together.
See `config/lerobot/README.md` for the schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.features.lerobot_export.models import ExportConfig, SourceConfig
from app.settings import get_settings

if TYPE_CHECKING:
    from app.settings import RecordingConfig

_VALID_FIELD_TYPES = ("list", "number", "struct")


def has_active_config(recording: RecordingConfig | None = None) -> bool:
    """Return True if the active recording config declares a `lerobot_export` mapping."""
    recording = recording if recording is not None else get_settings().recording
    return recording.lerobot_export is not None


def load_active_config(recording: RecordingConfig | None = None) -> ExportConfig:
    """Build the ExportConfig from the active recording config's `lerobot_export` section.

    Args:
        recording: Recording config to read (defaults to the active `RECORDING_CONFIG`).

    Raises:
        ValueError: If no `lerobot_export` mapping is configured, or it is malformed.
    """
    recording = recording if recording is not None else get_settings().recording
    if recording.lerobot_export is None:
        raise ValueError("No `lerobot_export` mapping is configured for the active recording config")
    return parse_config(recording.lerobot_export)


def parse_config(data: dict[str, Any]) -> ExportConfig:
    """Build an ExportConfig from a raw mapping dict.

    Raises:
        ValueError: If `images`, `observation`, or `action` is missing.
    """
    for key in ("images", "observation", "action"):
        if key not in data:
            raise ValueError(f"lerobot_export mapping must contain {key!r}")

    time_range = data.get("time_range", "intersection")
    if time_range not in ("intersection", "union"):
        raise ValueError(f"lerobot_export 'time_range' must be 'intersection' or 'union', got {time_range!r}")

    # Normalize structural errors (observation not a mapping, source missing
    # 'topic', etc.) to ValueError so the API returns 400 rather than 500.
    try:
        observation = {
            field_name: [_parse_source(s) for s in sources] for field_name, sources in data["observation"].items()
        }
        action = [_parse_source(s) for s in data["action"]]
    except (AttributeError, KeyError, TypeError) as e:
        raise ValueError(f"Malformed lerobot_export mapping: {e}") from e

    return ExportConfig(
        images=data["images"],
        observation=observation,
        action=action,
        fps=data.get("fps", 0),
        robot_type=data.get("robot_type", "custom"),
        sync_tolerance_ms=data.get("sync_tolerance_ms", 50.0),
        image_tolerance_ms=data.get("image_tolerance_ms", 200.0),
        time_range=time_range,
    )


def _parse_source(source: dict[str, Any]) -> SourceConfig:
    for required in ("topic", "field", "type"):
        if required not in source:
            raise ValueError(f"Source {source.get('topic', '?')!r} must specify {required!r}")
    field_type = source["type"]
    if field_type not in _VALID_FIELD_TYPES:
        raise ValueError(
            f"Source {source['topic']!r}: type {field_type!r} is invalid; "
            f"must be one of {_VALID_FIELD_TYPES}"
        )
    if field_type == "list" and "indices" not in source:
        raise ValueError(f"Source {source['topic']!r}: type 'list' requires 'indices'")
    if field_type == "struct" and "keys" not in source:
        raise ValueError(f"Source {source['topic']!r}: type 'struct' requires 'keys'")
    return SourceConfig(
        topic=source["topic"],
        field=source["field"],
        type=field_type,
        indices=source.get("indices"),
        keys=source.get("keys"),
        names=source.get("names"),
        interpolation=source.get("interpolation", "linear"),
    )
