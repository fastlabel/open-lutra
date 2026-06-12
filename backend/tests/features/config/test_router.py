"""Tests for the configuration and system info API endpoints.

NOTE: app.main requires rclpy, so this can only run inside Docker (make test).
"""

import pytest

rclpy = pytest.importorskip("rclpy", reason="rclpy is required (run via 'make test')")

from unittest.mock import MagicMock  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import set_monitor, set_recorder  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    """Creates a test client."""
    app = create_app()
    recorder = MagicMock()
    recorder.is_recording = False
    set_recorder(recorder)
    monitor = MagicMock()
    set_monitor(monitor)
    return TestClient(app)


class TestConfig:
    """Tests for GET /api/config."""

    def test_get_config(self, client: TestClient) -> None:
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "ros_domain_id" in data
        assert "robot_name" in data
        assert "default_topics" in data
        assert isinstance(data["default_topics"], list)
        assert isinstance(data["upload_enabled"], bool)


class TestHealth:
    """Tests for GET /api/health."""

    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
