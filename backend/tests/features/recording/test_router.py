"""Tests for the recording API endpoints.

NOTE: app.main requires rclpy, so this can only run inside Docker (make test).
"""

import pytest

rclpy = pytest.importorskip("rclpy", reason="rclpy is required (run via 'make test')")

from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import set_recorder  # noqa: E402
from app.features.recording import (  # noqa: E402
    AlreadyRecordingError,
    NotRecordingError,
    RecorderStatus,
    StopResult,
)
from app.main import create_app  # noqa: E402


@pytest.fixture
def mock_recorder() -> MagicMock:
    """Creates a mock recorder for testing."""
    recorder = MagicMock()
    recorder.is_recording = False
    recorder.start.return_value = Path("/data/output/20260205_120000")
    recorder.stop.return_value = StopResult(
        start_time=datetime(2026, 2, 5, 12, 0, 0),
        end_time=datetime(2026, 2, 5, 12, 1, 0),
        output_path=Path("/data/output/20260205_120000"),
    )
    recorder.get_status.return_value = RecorderStatus(is_recording=False)
    return recorder


@pytest.fixture
def client(mock_recorder: MagicMock) -> TestClient:
    """Creates a test client wired up to the mock recorder."""
    app = create_app()
    set_recorder(mock_recorder)
    return TestClient(app)


class TestRecordingStatus:
    """Tests for GET /api/recording/status."""

    def test_status_not_recording(self, client: TestClient) -> None:
        response = client.get("/api/recording/status")
        assert response.status_code == 200
        assert response.json()["is_recording"] is False

    def test_status_while_recording(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.get_status.return_value = RecorderStatus(
            is_recording=True,
            output_path=Path("/data/output/20260205_120000"),
            start_time=datetime(2026, 2, 5, 12, 0, 0),
            elapsed_sec=30.5,
        )
        response = client.get("/api/recording/status")
        assert response.status_code == 200
        data = response.json()
        assert data["is_recording"] is True
        assert data["elapsed_sec"] == 30.5

    def test_status_includes_output_path(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.get_status.return_value = RecorderStatus(
            is_recording=True,
            output_path=Path("/data/output/20260205_120000"),
            start_time=datetime(2026, 2, 5, 12, 0, 0),
            elapsed_sec=10.0,
        )
        response = client.get("/api/recording/status")
        assert response.json()["output_path"] == "/data/output/20260205_120000"


class TestStartRecording:
    """Tests for POST /api/recording/start."""

    def test_start_recording_success(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.get_status.return_value = RecorderStatus(
            is_recording=True,
            start_time=datetime(2026, 2, 5, 12, 0, 0),
            elapsed_sec=0.0,
        )
        response = client.post("/api/recording/start")
        assert response.status_code == 200
        assert "output_path" in response.json()

    def test_start_recording_crash_right_after_start_returns_explicit_500(
        self, client: TestClient, mock_recorder: MagicMock
    ) -> None:
        """A recorder that dies between start() and the status read returns a named error, not a bare 500."""
        # get_status() detected the crash and reset the state (start_time is None).
        mock_recorder.get_status.return_value = RecorderStatus(is_recording=False)
        response = client.post("/api/recording/start")
        assert response.status_code == 500
        assert "exited immediately after starting" in response.json()["detail"]

    def test_start_recording_with_topics(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.get_status.return_value = RecorderStatus(
            is_recording=True,
            start_time=datetime(2026, 2, 5, 12, 0, 0),
            elapsed_sec=0.0,
        )
        response = client.post("/api/recording/start", json={"topics": ["/robot_slave/states"]})
        assert response.status_code == 200
        mock_recorder.start.assert_called_with(
            topics=["/robot_slave/states"], qos_overrides=None, task_name=None, metadata=None
        )

    def test_start_recording_with_task_name(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.get_status.return_value = RecorderStatus(
            is_recording=True,
            start_time=datetime(2026, 2, 5, 12, 0, 0),
            elapsed_sec=0.0,
        )
        response = client.post("/api/recording/start", json={"topics": ["/topic"], "task_name": "pick"})
        assert response.status_code == 200
        mock_recorder.start.assert_called_with(
            topics=["/topic"], qos_overrides=None, task_name="pick", metadata=None
        )

    def test_start_recording_with_metadata(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.get_status.return_value = RecorderStatus(
            is_recording=True,
            start_time=datetime(2026, 2, 5, 12, 0, 0),
            elapsed_sec=0.0,
        )
        response = client.post(
            "/api/recording/start",
            json={"topics": ["/topic"], "metadata": {"operator_id": "op001"}},
        )
        assert response.status_code == 200
        mock_recorder.start.assert_called_with(
            topics=["/topic"], qos_overrides=None, task_name=None, metadata={"operator_id": "op001"}
        )

    def test_start_recording_already_recording(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.start.side_effect = AlreadyRecordingError("Already recording")
        response = client.post("/api/recording/start")
        assert response.status_code == 409
        assert "Already recording" in response.json()["detail"]

    def test_start_recording_response_contains_start_time(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.get_status.return_value = RecorderStatus(
            is_recording=True,
            start_time=datetime(2026, 2, 5, 12, 0, 0),
            elapsed_sec=0.0,
        )
        response = client.post("/api/recording/start")
        data = response.json()
        assert "start_time" in data


class TestStopRecording:
    """Tests for POST /api/recording/stop."""

    def test_stop_recording_success(self, client: TestClient) -> None:
        response = client.post("/api/recording/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["duration_sec"] == 60.0

    def test_stop_recording_not_recording(self, client: TestClient, mock_recorder: MagicMock) -> None:
        mock_recorder.stop.side_effect = NotRecordingError("Not currently recording")
        response = client.post("/api/recording/stop")
        assert response.status_code == 409
        assert "Not currently recording" in response.json()["detail"]

    def test_stop_recording_response_contains_times(self, client: TestClient) -> None:
        response = client.post("/api/recording/stop")
        data = response.json()
        assert "start_time" in data
        assert "end_time" in data
        assert "output_path" in data
