"""Tests for the topic monitoring API endpoints."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import set_monitor, set_recorder
from app.features.topics import (
    DiscoveredTopic,
    TopicInfo,
)
from app.main import create_app


@pytest.fixture
def mock_recorder() -> MagicMock:
    """Creates a mock recorder for testing."""
    recorder = MagicMock()
    recorder.is_recording = False
    return recorder


@pytest.fixture
def mock_monitor() -> MagicMock:
    """Creates a mock TopicMonitor for testing."""
    monitor = MagicMock()
    monitor.get_topic_stats.return_value = [
        TopicInfo(
            name="/robot_slave/states",
            msg_type="sensor_msgs/msg/JointState",
            actual_hz=99.3,
            status="ok",
            message_count=5230,
            is_subscribed=True,
            baseline_hz=100.0,
            baseline_fixed=True,
            loss_rate=0.0,
            drop_count=0,
            continuity_score=1.0,
            qos_reliability="RELIABLE",
        ),
    ]
    monitor.get_discovered_topics.return_value = [
        DiscoveredTopic(
            name="/rosout",
            msg_type="rcl_interfaces/msg/Log",
            is_subscribed=False,
        ),
    ]
    monitor.get_latest_message.return_value = {"data": [1.0, 2.0]}
    monitor.update_subscriptions.return_value = ["/robot_slave/states"]
    return monitor


@pytest.fixture
def client(mock_recorder: MagicMock, mock_monitor: MagicMock) -> TestClient:
    """Creates a test client wired up to the mock services."""
    app = create_app()
    set_recorder(mock_recorder)
    set_monitor(mock_monitor)
    return TestClient(app)


class TestListTopics:
    """Tests for GET /api/topics."""

    def test_list_topics(self, client: TestClient) -> None:
        response = client.get("/api/topics")
        assert response.status_code == 200
        data = response.json()
        assert "topics" in data
        assert "discovered_topics" in data
        assert len(data["topics"]) == 1
        assert data["topics"][0]["name"] == "/robot_slave/states"

    def test_list_topics_includes_discovered(self, client: TestClient) -> None:
        response = client.get("/api/topics")
        data = response.json()
        assert len(data["discovered_topics"]) == 1
        assert data["discovered_topics"][0]["name"] == "/rosout"


class TestLatestMessage:
    """Tests for GET /api/topics/message."""

    def test_get_latest_message(self, client: TestClient) -> None:
        response = client.get("/api/topics/message?topic=/robot_slave/states")
        assert response.status_code == 200
        assert response.json() == {"message": {"data": [1.0, 2.0]}}

    def test_get_latest_message_no_message_yet(self, client: TestClient, mock_monitor: MagicMock) -> None:
        """Returns 200 + message=null when nothing has been received yet (not 404).

        With on-demand capture, the first call always returns null, so this is
        treated as a successful response rather than an error.
        """
        mock_monitor.get_latest_message.return_value = None
        response = client.get("/api/topics/message?topic=/unknown")
        assert response.status_code == 200
        assert response.json() == {"message": None}


class TestUpdateSubscriptions:
    """Tests for PUT /api/topics/subscriptions."""

    def test_update_subscriptions(self, client: TestClient) -> None:
        response = client.put(
            "/api/topics/subscriptions",
            json={"topics": ["/robot_slave/states"]},
        )
        assert response.status_code == 200
        assert response.json()["subscribed"] == ["/robot_slave/states"]
