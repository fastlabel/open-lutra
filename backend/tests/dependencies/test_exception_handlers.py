"""Tests for the exception handlers.

Verifies that each recording exception is mapped to the correct HTTP status code.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dependencies import set_recorder
from app.dependencies.services import get_recorder
from app.features.recording import AlreadyRecordingError, NotRecordingError, RecorderError
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Test client for exception tests."""
    app = create_app()
    recorder = MagicMock()
    recorder.is_recording = False
    set_recorder(recorder)
    return TestClient(app)


class TestAlreadyRecordingHandler:
    """AlreadyRecordingError -> 409 Conflict."""

    def test_returns_409(self, client: TestClient) -> None:
        recorder = get_recorder()
        recorder.start.side_effect = AlreadyRecordingError("Already recording")
        response = client.post("/api/recording/start")
        assert response.status_code == 409
        assert response.json()["detail"] == "Already recording"


class TestNotRecordingHandler:
    """NotRecordingError -> 409 Conflict."""

    def test_returns_409(self, client: TestClient) -> None:
        recorder = get_recorder()
        recorder.stop.side_effect = NotRecordingError("Not currently recording")
        response = client.post("/api/recording/stop")
        assert response.status_code == 409
        assert response.json()["detail"] == "Not currently recording"


class TestRecorderErrorHandler:
    """RecorderError -> 500 Internal Server Error."""

    def test_returns_500(self, client: TestClient) -> None:
        recorder = get_recorder()
        recorder.start.side_effect = RecorderError("Internal error")
        response = client.post("/api/recording/start")
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal error"


class TestCatchAllHandler:
    """Unexpected exceptions -> 500 naming the exception instead of a bare 'Internal Server Error'."""

    @pytest.fixture
    def raw_client(self) -> TestClient:
        """Client that returns the 500 response instead of re-raising server exceptions."""
        app = create_app()
        recorder = MagicMock()
        recorder.is_recording = False
        set_recorder(recorder)
        return TestClient(app, raise_server_exceptions=False)

    def test_names_exception_type_and_message(self, raw_client: TestClient) -> None:
        recorder = get_recorder()
        recorder.start.side_effect = ValueError("boom")
        response = raw_client.post("/api/recording/start")
        assert response.status_code == 500
        assert "ValueError: boom" in response.json()["detail"]

    def test_falls_back_to_type_for_empty_message(self, raw_client: TestClient) -> None:
        recorder = get_recorder()
        recorder.start.side_effect = RuntimeError()
        response = raw_client.post("/api/recording/start")
        assert response.status_code == 500
        assert "RuntimeError" in response.json()["detail"]
