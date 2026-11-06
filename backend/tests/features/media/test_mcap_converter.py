"""Tests for the pure helpers in mcap_converter.

The MCAP-reading / ffmpeg-piping functions are marked ``pragma: no cover``; this
covers the pure helpers (timestamp sorting and the fallback log line) and forces
the module to import so its module-level definitions are measured.
"""

import logging

import pytest

from app.features.media.mcap_converter import _JointTopicData, _log_fallback, _sort_topic_data
from app.infra.video import VideoEncodeError


def test_sort_topic_data_empty() -> None:
    data = _JointTopicData(timestamps=[], positions=[], joint_count=0)
    assert _sort_topic_data(data) == ([], [])


def test_sort_topic_data_orders_by_timestamp() -> None:
    data = _JointTopicData(timestamps=[30, 10, 20], positions=[[3.0], [1.0], [2.0]], joint_count=1)
    timestamps, positions = _sort_topic_data(data)
    assert timestamps == [10, 20, 30]
    assert positions == [[1.0], [2.0], [3.0]]


def test_fallback_is_logged_with_both_encoders_and_the_reason(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        _log_fallback(
            "cam.mp4", "nvenc", "libx264", VideoEncodeError("ffmpeg failed (code=1): OpenEncodeSessionEx failed")
        )
    assert caplog.messages == [
        "Encoding cam.mp4 with nvenc failed; retrying with libx264: ffmpeg failed (code=1): OpenEncodeSessionEx failed"
    ]
