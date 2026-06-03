"""Active set (params) for builtin validators.

Validators and their parameters are configured via the `validators:` section
of the robot config YAML (e.g. `config/simulator.yaml`). This module reads
that configuration and instantiates the corresponding builtin classes.

If you add a new builtin validator, register it in `_BUILTIN_REGISTRY` below.
Custom validators (placed under `custom/` with `@register_validator`) are
handled separately by the registry module and are not configured here.
"""

from app.features.validation.base import RecordingValidator
from app.features.validation.builtins import RequiredTopicsPresent, TotalDurationSec
from app.settings import Settings, get_settings

_BUILTIN_CLASSES: list[type[RecordingValidator]] = [RequiredTopicsPresent, TotalDurationSec]
_BUILTIN_REGISTRY: dict[str, type[RecordingValidator]] = {cls.name: cls for cls in _BUILTIN_CLASSES}


def get_builtin_recording_validators(settings: Settings | None = None) -> list[RecordingValidator]:
    """Return instantiated builtin validators from the robot config.

    Each entry in `validators:` is looked up by name in `_BUILTIN_REGISTRY`
    and instantiated with the remaining fields as keyword arguments.

    Raises ValueError for unknown validator names so misconfiguration is
    caught at startup rather than silently skipped.
    """
    s = settings or get_settings()
    result: list[RecordingValidator] = []
    for entry in s.robot.validators:
        cls = _BUILTIN_REGISTRY.get(entry.name)
        if cls is None:
            raise ValueError(
                f"Unknown builtin validator: {entry.name!r}. "
                f"Available: {sorted(_BUILTIN_REGISTRY)}"
            )
        result.append(cls(**entry.params))
    return result
