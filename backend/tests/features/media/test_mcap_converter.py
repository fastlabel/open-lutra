"""Tests for the pure helpers in mcap_converter.

The MCAP-reading / ffmpeg-piping functions are marked ``pragma: no cover``; this
covers the pure timestamp-sorting helper (and forces the module to import so its
module-level definitions are measured).
"""

from app.features.media.mcap_converter import _JointTopicData, _sort_topic_data


def test_sort_topic_data_empty() -> None:
    data = _JointTopicData(timestamps=[], positions=[], joint_count=0)
    assert _sort_topic_data(data) == ([], [])


def test_sort_topic_data_orders_by_timestamp() -> None:
    data = _JointTopicData(timestamps=[30, 10, 20], positions=[[3.0], [1.0], [2.0]], joint_count=1)
    timestamps, positions = _sort_topic_data(data)
    assert timestamps == [10, 20, 30]
    assert positions == [[1.0], [2.0], [3.0]]
