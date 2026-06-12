"""Field extraction and image decoding for LeRobot export.

`extract_field_data` resolves a dot-separated field path on a decoded message
and returns a float64 ndarray according to an explicit type declaration.
`decode_ros_image` turns an Image / CompressedImage into an RGB ndarray.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

if TYPE_CHECKING:
    from numpy.typing import NDArray

_VALID_FIELD_TYPES = ("list", "number", "struct")


def extract_field_data(
    decoded: Any,
    field: str,
    field_type: str,
    indices: list[int] | None = None,
    keys: list[str] | None = None,
) -> NDArray[np.float64]:
    """Extract a float vector from a decoded telemetry message.

    Traverses `field` as a dot-separated attribute path (e.g.
    "joint_state.position", "gripper_pos", "pose.position"), then extracts
    values according to `field_type`:

    - "number": scalar float/int → 1-element array.
    - "list":   numeric sequence → elements selected by `indices` (required);
                out-of-range indices are filled with 0.0.
    - "struct": named-field object (e.g. geometry_msgs/Point) → attributes
                named by `keys` extracted in order (required).

    Raises:
        ValueError: When the path is not found, `field_type` is unknown, or
            `indices` / `keys` is missing for "list" / "struct" respectively.
    """
    if field_type not in _VALID_FIELD_TYPES:
        raise ValueError(f"Unknown field type {field_type!r}; must be one of {_VALID_FIELD_TYPES}")

    obj: Any = decoded
    for part in field.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError as e:
            raise ValueError(f"Message has no field {field!r} (missing attribute {part!r})") from e

    if field_type == "number":
        return np.array([float(obj)], dtype=np.float64)

    if field_type == "struct":
        if keys is None:
            raise ValueError(f"Field {field!r} has type 'struct' but 'keys' is not specified")
        try:
            return np.array([float(getattr(obj, k)) for k in keys], dtype=np.float64)
        except AttributeError as e:
            raise ValueError(f"Field {field!r}: {e}") from e

    # type == "list"
    if indices is None:
        raise ValueError(f"Field {field!r} has type 'list' but 'indices' is not specified")
    arr = np.asarray(list(obj), dtype=np.float64)
    return np.array([arr[i] if 0 <= i < len(arr) else 0.0 for i in indices], dtype=np.float64)


def decode_ros_image(decoded: Any) -> NDArray[np.uint8]:
    """Decode an Image / CompressedImage message into an (H, W, 3) RGB ndarray.

    CompressedImage is detected by the presence of a `format` field (decoded via
    PIL); raw `sensor_msgs/Image` by the presence of an `encoding` field.

    Raises:
        ValueError: For an unsupported raw-image encoding, or a non-image message.
    """
    # CompressedImage: `format` holds e.g. "rgb8; jpeg compressed"; decode via PIL.
    if hasattr(decoded, "format"):
        img = Image.open(io.BytesIO(bytes(decoded.data)))
        return np.asarray(img.convert("RGB"), dtype=np.uint8)

    if not hasattr(decoded, "encoding"):
        raise ValueError("Message is not an image (no format or encoding field)")

    encoding = decoded.encoding
    height, width = decoded.height, decoded.width
    raw = np.frombuffer(bytes(decoded.data), dtype=np.uint8)

    if encoding in ("rgb8", "bgr8"):
        rgb = raw.reshape(height, width, 3)
        return np.ascontiguousarray(rgb[:, :, ::-1] if encoding == "bgr8" else rgb, dtype=np.uint8)
    if encoding in ("rgba8", "bgra8"):
        order = [2, 1, 0] if encoding == "bgra8" else [0, 1, 2]
        return np.ascontiguousarray(raw.reshape(height, width, 4)[:, :, order], dtype=np.uint8)
    if encoding in ("mono8", "8UC1"):
        gray = raw.reshape(height, width)
        return np.ascontiguousarray(np.stack([gray] * 3, axis=-1), dtype=np.uint8)
    if encoding in ("mono16", "16UC1"):
        raw16 = np.frombuffer(bytes(decoded.data), dtype=np.uint16).reshape(height, width)
        scaled = (raw16 / 256).astype(np.uint8)
        return np.ascontiguousarray(np.stack([scaled] * 3, axis=-1), dtype=np.uint8)
    raise ValueError(f"Unsupported image encoding: {encoding!r}")
