"""Tests for the recordings API endpoints (query-parameter wiring)."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.features.recordings.schemas import FileEntry
from app.main import create_app

# 2026-11-04 00:00:00 JST
DAY_START_NS = 1_793_718_000_000_000_000
HOUR_NS = 3_600 * 1_000_000_000


def _entry(name: str, recording_start_ns: int | None) -> FileEntry:
    return FileEntry(
        name=name,
        path=name,
        size=1,
        modified_at=0.0,
        topic_count=None,
        recording_start_ns=recording_start_ns,
        duration_ns=None,
        message_count=None,
        has_quality_report=False,
        validation_overall_status=None,
        upload_status=None,
        task_name=None,
        recording_config_name=None,
        tags=[],
        metadata={},
    )


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Test client whose output directory scan returns a fixed set of recordings."""
    entries = [
        _entry("pm", DAY_START_NS + 13 * HOUR_NS),
        _entry("am", DAY_START_NS + 9 * HOUR_NS),
        _entry("no_meta", None),
    ]
    with (
        patch("app.features.recordings.router.get_settings", return_value=SimpleNamespace(output_dir=tmp_path)),
        patch("app.features.recordings.router.scan_output_dir", return_value=entries),
    ):
        yield TestClient(create_app())


class TestListRecordings:
    """Tests for GET /api/recordings."""

    def test_without_bounds_returns_everything(self, client: TestClient) -> None:
        response = client.get("/api/recordings")

        assert response.status_code == 200
        assert [e["name"] for e in response.json()["entries"]] == ["pm", "am", "no_meta"]

    def test_filters_by_start_time(self, client: TestClient) -> None:
        response = client.get(
            "/api/recordings",
            params={"started_after": "2026-11-04T00:00:00+09:00", "started_before": "2026-11-04T12:00:00+09:00"},
        )

        assert response.status_code == 200
        assert [e["name"] for e in response.json()["entries"]] == ["am"]

    @pytest.mark.parametrize(
        "params",
        [
            {"started_after": "2026-11-04T00:00:00"},
            {"started_after": "2026-11-04T12:00:00+09:00", "started_before": "2026-11-04T00:00:00+09:00"},
        ],
    )
    def test_invalid_bounds_are_rejected(self, client: TestClient, params: dict[str, str]) -> None:
        response = client.get("/api/recordings", params=params)

        assert response.status_code == 422
