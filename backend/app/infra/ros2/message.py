"""ROS2 message conversion utilities.

Converts ROS2 message objects to JSON-safe dicts, replacing binary data
and very large lists with summary representations.
"""

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

_MAX_BYTES_PREVIEW = 64
_MAX_LIST_PREVIEW = 20


def sanitize_value(value: Any) -> Any:
    """Convert a message field value to a JSON-safe form."""
    if isinstance(value, bytes):
        if len(value) <= _MAX_BYTES_PREVIEW:
            return value.hex()
        return f"<bytes: {len(value):,}B>"
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_LIST_PREVIEW:
            preview = [sanitize_value(v) for v in value[:_MAX_LIST_PREVIEW]]
            return {
                "__truncated": True,
                "length": len(value),
                "preview": preview,
            }
        return [sanitize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_value(v) for k, v in value.items()}
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
    return value


def msg_to_dict(msg: Any) -> dict[str, Any]:  # pragma: no cover
    """Convert a ROS2 message into a JSON-safe dict."""
    try:
        from rosidl_runtime_py.convert import message_to_ordereddict

        raw = message_to_ordereddict(msg)
        return sanitize_value(raw)  # type: ignore[no-any-return]
    except (ImportError, AttributeError, TypeError) as e:
        return {"__error": f"Failed to convert message: {e}"}


def import_message_class(msg_type_str: str) -> type[Any] | None:  # pragma: no cover
    """Dynamically import a class from a ROS2 message type string.

    Args:
        msg_type_str: e.g. "sensor_msgs/msg/JointState"

    Returns:
        The message class, or None if the import fails.
    """
    try:
        from rosidl_runtime_py.utilities import get_message

        return get_message(msg_type_str)  # type: ignore[no-any-return]
    except (ImportError, AttributeError, ModuleNotFoundError) as e:
        logger.warning("Failed to import message type: %s (%s)", msg_type_str, e)
        return None
