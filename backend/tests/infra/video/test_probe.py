"""Tests for resolving the configured encoder against the NVENC probe result."""

import pytest

from app.infra.video import VideoEncoder
from app.infra.video.probe import resolve_encoder


@pytest.mark.parametrize(
    ("requested", "nvenc_usable", "expected"),
    [
        ("libx264", False, "libx264"),
        ("libx264", True, "libx264"),
        ("nvenc", True, "nvenc"),
        ("nvenc", False, "libx264"),
    ],
)
def test_resolve_encoder(requested: VideoEncoder, nvenc_usable: bool, expected: VideoEncoder) -> None:
    assert resolve_encoder(requested, nvenc_usable) == expected
