"""Lightweight fakes for decoded ROS2 messages used across export tests.

Avoids any rclpy/mcap dependency: the converter and writer only touch attributes
(`position`, `data`, `format`, `encoding`, ...), so plain objects suffice.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from app.features.lerobot_export.converter import TimestampedMessage


class FakeJointState:
    """Stand-in for sensor_msgs/JointState."""

    def __init__(
        self,
        position: list[float] | None = None,
        velocity: list[float] | None = None,
        effort: list[float] | None = None,
        name: list[str] | None = None,
    ) -> None:
        if position is not None:
            self.position = position
        if velocity is not None:
            self.velocity = velocity
        if effort is not None:
            self.effort = effort
        if name is not None:
            self.name = name


class FakeFloatArray:
    """Stand-in for std_msgs/Float64MultiArray (and Float32)."""

    def __init__(self, data: list[float]) -> None:
        self.data = data


class FakeCompressedImage:
    """Stand-in for sensor_msgs/CompressedImage (PNG-encoded payload)."""

    def __init__(self, data: bytes, fmt: str = "rgb8; png compressed") -> None:
        self.format = fmt
        self.data = data


class FakeRawImage:
    """Stand-in for sensor_msgs/Image (raw payload)."""

    def __init__(self, encoding: str, height: int, width: int, data: bytes) -> None:
        self.encoding = encoding
        self.height = height
        self.width = width
        self.data = data


def make_png_bytes(rgb: np.ndarray) -> bytes:
    """Encode an (H, W, 3) uint8 array as PNG bytes."""
    buffer = io.BytesIO()
    Image.fromarray(rgb.astype(np.uint8), mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def make_image_message(height: int = 2, width: int = 2, value: int = 128) -> FakeCompressedImage:
    """Build a small solid-color compressed image message."""
    rgb = np.full((height, width, 3), value, dtype=np.uint8)
    return FakeCompressedImage(make_png_bytes(rgb))


def joint_message(timestamp_ns: int, position: list[float]) -> TimestampedMessage:
    """Build a TimestampedMessage carrying a FakeJointState."""
    return TimestampedMessage(timestamp_ns=timestamp_ns, decoded=FakeJointState(position=position))


def image_message(timestamp_ns: int, value: int = 128, size: int = 2) -> TimestampedMessage:
    """Build a TimestampedMessage carrying a small compressed image."""
    return TimestampedMessage(timestamp_ns=timestamp_ns, decoded=make_image_message(size, size, value))
