"""Tests for the configuration and system info API endpoints."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import set_monitor, set_recorder
from app.main import create_app
from app.settings import get_settings
from app.shared.disk import DiskUsage


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

    def test_reports_the_output_volume_capacity(self, client: TestClient) -> None:
        usage = DiskUsage(total_bytes=1_000_000, used_bytes=400_000, free_bytes=550_000)
        with patch("app.features.config.router.read_disk_usage", return_value=usage):
            response = client.get("/api/system/storage")

        assert response.status_code == 200
        data = response.json()
        assert data["path"] == str(get_settings().output_dir)
        assert data["total_bytes"] == 1_000_000
        assert data["used_bytes"] == 400_000
        assert data["free_bytes"] == 550_000

    def test_uninspectable_volume_returns_null_counts(self, client: TestClient) -> None:
        with patch("app.features.config.router.read_disk_usage", return_value=None):
            response = client.get("/api/system/storage")

        assert response.status_code == 200
        data = response.json()
        assert data["total_bytes"] is None
        assert data["used_bytes"] is None
        assert data["free_bytes"] is None


class TestHealth:
    """Tests for GET /api/health."""

    def test_health_check(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
