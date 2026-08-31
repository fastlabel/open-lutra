"""Tests for the configuration and system info API endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import set_monitor, set_recorder
from app.main import create_app
from app.settings import get_settings


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


class TestStorage:
    """Tests for GET /api/system/storage."""

    def test_reports_the_output_volume_free_space(self, client: TestClient) -> None:
        with patch("app.features.config.router.read_free_bytes", return_value=550_000):
            response = client.get("/api/system/storage")

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == str(get_settings().output_dir)
        assert data["free_bytes"] == 550_000

    def test_uninspectable_volume_returns_a_null_count(self, client: TestClient) -> None:
        with patch("app.features.config.router.read_free_bytes", return_value=None):
            response = client.get("/api/system/storage")

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == str(get_settings().output_dir)
        assert data["free_bytes"] is None


class TestHealth:
    """Tests for GET /api/health."""

    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
