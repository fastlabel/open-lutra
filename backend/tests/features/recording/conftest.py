"""Shared fixtures for the recording feature tests."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.features.recording import ROS2BagRecorder


@pytest.fixture
def settings() -> MagicMock:
    """Test Settings."""
    s = MagicMock()
    s.output_dir = Path("/tmp/test_output")
    s.default_topics = ["/joint_states", "/camera/color/image_raw/compressed"]
    s.recording_discovery_timeout = 10
    s.recording_start_delay_sec = 0.0
    s.recording_config = "config/simulator.yaml"
    return s


@pytest.fixture
def mock_ros2() -> MagicMock:
    """Test ROS2Command mock.

    bag_record() returns a RecordProcess mock.
    record.process corresponds to the actual subprocess process.
    """
    ros2 = MagicMock()
    mock_record = MagicMock()
    mock_record.process = MagicMock()
    mock_record.process.poll.return_value = None  # Default: process is running
    mock_record.wait_for_subscriptions.return_value = []
    ros2.bag_record.return_value = mock_record
    return ros2


@pytest.fixture
def recorder(settings: MagicMock, mock_ros2: MagicMock) -> ROS2BagRecorder:
    """Test ROS2BagRecorder."""
    return ROS2BagRecorder(settings, mock_ros2)
