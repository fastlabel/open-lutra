"""Structure-based detection and extraction utilities for MCAP messages.

Determines whether a message is an image or a JointState based on the structure
of the message object (presence of attributes), without depending on ROS2 type
names. Also handles custom message types that nest a JointState inside a
`joint_state` field.
"""

from typing import Any


def is_image_message(decoded: Any) -> bool:
    """Return True if the message looks like an image (e.g., `CompressedImage` / `Image`).

    Detection is based on the presence of `format` + `data` (bytes) fields and
    does not depend on the message type name (e.g., `sensor_msgs/msg/Image`).
    """
    return hasattr(decoded, "format") and hasattr(decoded, "data") and isinstance(decoded.data, (bytes, bytearray))


def extract_joint_positions(decoded: Any) -> list[float]:
    """Extract a list of position values from a `JointState`-like message.

    Supported patterns:
      - Standard `sensor_msgs/msg/JointState`: `decoded.position` / `decoded.name`
      - Custom types that wrap a JointState: `decoded.joint_state.position`
      - Composite custom types: `decoded.joint_state.position` +
        `decoded.neck_joint_state.position` concatenated in order

    Returns an empty list if none of the patterns match.
    """
    positions: list[float] = []

    if hasattr(decoded, "joint_state") and hasattr(decoded.joint_state, "position"):
        positions.extend(decoded.joint_state.position)
    elif hasattr(decoded, "position"):
        positions.extend(decoded.position)

    # Neck joints for composite types (appended only if present)
    if hasattr(decoded, "neck_joint_state") and hasattr(decoded.neck_joint_state, "position"):
        positions.extend(decoded.neck_joint_state.position)

    return positions


def extract_joint_names(decoded: Any) -> list[str]:
    """Extract a list of joint names from a `JointState`-like message.

    Names are returned in the same order as `extract_joint_positions`.
    Returns an empty list if no names are available (no `name` attribute).
    """
    names: list[str] = []

    if hasattr(decoded, "joint_state") and hasattr(decoded.joint_state, "name"):
        names.extend(decoded.joint_state.name)
    elif hasattr(decoded, "name"):
        names.extend(decoded.name)

    if hasattr(decoded, "neck_joint_state") and hasattr(decoded.neck_joint_state, "name"):
        names.extend(decoded.neck_joint_state.name)

    return names
