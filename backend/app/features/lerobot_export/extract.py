"""Field extraction and image decoding for LeRobot export.

Both are structure-based (no ROS2 type names), matching the rest of the project
(`app/infra/mcap`). `extract_field_data` reads a numeric vector from a decoded
message; `decode_ros_image` turns an Image / CompressedImage into an RGB ndarray.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import numpy as np
from PIL import Image

from app.infra.mcap import extract_joint_positions

if TYPE_CHECKING:
    from numpy.typing import NDArray


def extract_field_data(
    decoded: Any,
    field: str | None,
    indices: list[int] | None = None,
) -> NDArray[np.float64]:
    """Extract a float vector from a decoded telemetry message.

    When `field` is None, the vector is detected by structure: joint positions
    via `extract_joint_positions` (which also handles nested `joint_state` and
    composite `neck_joint_state` custom messages), falling back to a `data`
    field (Float*MultiArray or scalar std_msgs/Float64). Set `field` to override
    (e.g. "velocity", "effort", "data", or a custom attribute).

    Scalar sources (e.g. a `std_msgs/Float64` gripper value) are normalized to a
    length-1 vector. Out-of-range `indices` are filled with 0.0 to keep a
    fixed-length vector.

    Raises:
        ValueError: When no vector can be extracted, or `field` is absent.
    """
    if field is None:
        raw: Any = extract_joint_positions(decoded)
        if not len(raw) and hasattr(decoded, "data"):
            raw = decoded.data
    else:
        raw = getattr(decoded, field, None)
        if raw is None:
            raise ValueError(f"Message has no field {field!r}")

    # np.atleast_1d normalizes scalars (std_msgs/Float64 .data) to shape (1,)
    # while leaving list/array sources as a flat vector.
    arr = np.atleast_1d(np.asarray(raw, dtype=np.float64))
    if field is None and arr.size == 0:
        raise ValueError("Cannot extract a vector (no joint position or 'data' field); set 'field' in the config")
    if indices is None:
        return arr
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
