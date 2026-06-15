"""Active set (params) for builtin validators.

Validators and their parameters are configured via the `validators:` section
of the recording config YAML (e.g. `config/simulator.yaml`). This module
reads that configuration and instantiates the corresponding builtin classes.

If you add a new builtin validator, register it in `_BUILTIN_REGISTRY` below.
Custom validators (placed under `custom/` with `@register_validator`) are
handled separately by the registry module and are not configured here.
"""

import inspect
from typing import ClassVar

from app.features.validation.base import RecordingValidator, ValidationResult
from app.features.validation.builtins import RequiredTopicsPresent, TotalDurationSec
from app.features.validation.context import ValidationContext
from app.settings import Settings, get_settings

_BUILTIN_CLASSES: list[type[RecordingValidator]] = [RequiredTopicsPresent, TotalDurationSec]
_BUILTIN_REGISTRY: dict[str, type[RecordingValidator]] = {cls.name: cls for cls in _BUILTIN_CLASSES}


def _make_config_error_validator(entry_name: str, message: str) -> RecordingValidator:
    """Return a validator that always reports status=error with the given message.

    Used when a YAML entry cannot be instantiated due to misconfiguration, so
    the remaining entries still run instead of aborting the whole set.
    """

    class _ConfigError(RecordingValidator):
        name: ClassVar[str] = entry_name

        def validate(self, _ctx: ValidationContext) -> ValidationResult:
            return ValidationResult(status="error", message=message)

    return _ConfigError()


def get_builtin_recording_validators(settings: Settings | None = None) -> list[RecordingValidator]:
    """Return instantiated builtin validators from the recording config.

    Each entry in `validators:` is looked up by name in `_BUILTIN_REGISTRY`
    and instantiated with the remaining fields as keyword arguments.

    Misconfigured entries (unknown name or wrong constructor args) become
    error-returning validators so the remaining entries still run.
    """
    s = settings or get_settings()
    result: list[RecordingValidator] = []
    for entry in s.recording.validators:
        cls = _BUILTIN_REGISTRY.get(entry.name)
        if cls is None:
            result.append(
                _make_config_error_validator(
                    entry.name,
                    f"Unknown builtin validator: {entry.name!r}. "
                    f"Available: {sorted(_BUILTIN_REGISTRY)}",
                )
            )
            continue
        try:
            result.append(cls(**entry.params))
        except TypeError as e:
            valid_params = [
                p for p in inspect.signature(cls.__init__).parameters if p != "self"
            ]
            # Strip the "ClassName.__init__() " prefix from the TypeError message.
            detail = str(e)
            if ".__init__()" in detail:
                detail = detail.split(".__init__()", 1)[1].lstrip(" :")
            result.append(
                _make_config_error_validator(
                    entry.name,
                    f"Invalid params for validator {entry.name!r}: "
                    f"{detail}. Valid params: {valid_params}",
                )
            )
    return result
