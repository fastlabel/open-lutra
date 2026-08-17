"""Shared fixtures for the topic monitoring tests."""

from unittest.mock import MagicMock

import pytest

from app.features.topics.service import TopicMonitorService
from app.shared.log_manager import LogManager


@pytest.fixture
def log_manager() -> LogManager:
    """Test LogManager."""
    return LogManager(max_entries=100)


@pytest.fixture
def mock_subscriber() -> MagicMock:
    """Test TopicSubscriber mock."""
    subscriber = MagicMock()
    subscriber.discover_topics.return_value = []
    subscriber.subscribe_topic.return_value = "RELIABLE"
    subscriber.convert_message.return_value = {"data": "test"}
    return subscriber


@pytest.fixture
def monitor(log_manager: LogManager, mock_subscriber: MagicMock) -> TopicMonitorService:
    """Test TopicMonitorService (subscriber preconfigured)."""
    service = TopicMonitorService(
        subscribed_topics=["/joint_states"],
        log_manager=log_manager,
        gap_threshold_sec=3.0,
    )
    service.set_subscriber(mock_subscriber)
    return service
