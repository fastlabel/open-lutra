"""Tests for the system update API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.dependencies import set_monitor, set_recorder
from app.features.system_update.agent_client import AgentUnavailableError, NoPendingUpdateError
from app.features.system_update.schemas import SystemUpdateStatus
from app.main import create_app

_ROUTER = "app.features.system_update.router"


@pytest.fixture
def recorder() -> MagicMock:
    recorder = MagicMock()
    recorder.is_recording = False
    return recorder


@pytest.fixture
def client(recorder: MagicMock) -> TestClient:
    app = create_app()
    set_recorder(recorder)
    set_monitor(MagicMock())
    return TestClient(app)


class TestGetSystemUpdate:
    def test_returns_agent_status(self, client: TestClient) -> None:
        status = SystemUpdateStatus(enabled=True, available=True, applying=False)
        with patch(f"{_ROUTER}.fetch_status", AsyncMock(return_value=status)):
            response = client.get("/api/system/update")
        assert response.status_code == 200
        assert response.json() == {"enabled": True, "available": True, "applying": False}

    def test_disabled_by_default(self, client: TestClient) -> None:
        response = client.get("/api/system/update")
        assert response.json() == {"enabled": False, "available": False, "applying": False}


class TestApplySystemUpdate:
    def test_applies(self, client: TestClient) -> None:
        status = SystemUpdateStatus(enabled=True, available=True, applying=True)
        with patch(f"{_ROUTER}.apply_update", AsyncMock(return_value=status)):
            response = client.post("/api/system/update/apply")
        assert response.status_code == 202
        assert response.json()["applying"] is True

    def test_rejects_while_recording(self, client: TestClient, recorder: MagicMock) -> None:
        recorder.is_recording = True
        apply = AsyncMock()
        with patch(f"{_ROUTER}.apply_update", apply):
            response = client.post("/api/system/update/apply")
        assert response.status_code == 409
        apply.assert_not_called()

    def test_no_pending_update(self, client: TestClient) -> None:
        with patch(f"{_ROUTER}.apply_update", AsyncMock(side_effect=NoPendingUpdateError)):
            response = client.post("/api/system/update/apply")
        assert response.status_code == 409

    def test_agent_unavailable(self, client: TestClient) -> None:
        with patch(f"{_ROUTER}.apply_update", AsyncMock(side_effect=AgentUnavailableError("down"))):
            response = client.post("/api/system/update/apply")
        assert response.status_code == 503
