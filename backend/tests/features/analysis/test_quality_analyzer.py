"""Tests for the QualityAnalyzer lifecycle facade.

The actual MCAP analysis runs on the JobQueue; this covers the facade's state
transitions. A cached report is materialized as a real ``quality_report.json``
(so ``load_report`` returns a valid model), and the queue is mocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.features.analysis.quality_analyzer import QualityAnalyzer, get_quality_analyzer
from app.features.jobs.models import JobStatus

_QUEUE_PATH = "app.features.analysis.quality_analyzer.get_job_queue"


def _write_quality_report(directory: Path) -> None:
    payload = {
        "duration_sec": 60.0,
        "total_messages": 0,
        "total_topics": 0,
        "file_size_bytes": 0,
        "topics": [],
    }
    (directory / "quality_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _queue(active: object | None = None) -> MagicMock:
    queue = MagicMock()
    queue.get_active_quality_job.return_value = active
    queue.enqueue_quality = AsyncMock()
    return queue


class TestQualityAnalyzerGet:
    async def test_returns_ready_when_cached(self, tmp_path: Path) -> None:
        _write_quality_report(tmp_path)
        result = await QualityAnalyzer().get(tmp_path)
        assert result.status == "ready"
        assert result.report is not None

    async def test_returns_analyzing_when_job_running(self, tmp_path: Path) -> None:
        active = MagicMock(status=JobStatus.RUNNING)
        with patch(_QUEUE_PATH, return_value=_queue(active)):
            result = await QualityAnalyzer().get(tmp_path)
        assert result.status == "analyzing"

    async def test_returns_error_when_job_failed(self, tmp_path: Path) -> None:
        active = MagicMock(status=JobStatus.FAILED, error="boom")
        with patch(_QUEUE_PATH, return_value=_queue(active)):
            result = await QualityAnalyzer().get(tmp_path)
        assert result.status == "error"
        assert result.error == "boom"

    async def test_returns_error_with_default_message(self, tmp_path: Path) -> None:
        active = MagicMock(status=JobStatus.FAILED, error=None)
        with patch(_QUEUE_PATH, return_value=_queue(active)):
            result = await QualityAnalyzer().get(tmp_path)
        assert result.status == "error"
        assert result.error is not None and "failed" in result.error.lower()

    async def test_returns_not_found_when_nothing(self, tmp_path: Path) -> None:
        with patch(_QUEUE_PATH, return_value=_queue(None)):
            result = await QualityAnalyzer().get(tmp_path)
        assert result.status == "not_found"


class TestQualityAnalyzerStart:
    async def test_returns_ready_when_cached(self, tmp_path: Path) -> None:
        _write_quality_report(tmp_path)
        result = await QualityAnalyzer().start(tmp_path)
        assert result.status == "ready"

    async def test_returns_analyzing_when_job_running(self, tmp_path: Path) -> None:
        active = MagicMock(status=JobStatus.RUNNING)
        with patch(_QUEUE_PATH, return_value=_queue(active)):
            result = await QualityAnalyzer().start(tmp_path)
        assert result.status == "analyzing"

    async def test_returns_not_found_when_no_mcap(self, tmp_path: Path) -> None:
        with patch(_QUEUE_PATH, return_value=_queue(None)):
            result = await QualityAnalyzer().start(tmp_path)
        assert result.status == "not_found"
        assert result.error == "MCAP file not found"

    async def test_enqueues_when_mcap_present(self, tmp_path: Path) -> None:
        (tmp_path / "rec.mcap").write_bytes(b"")
        queue = _queue(None)
        with patch(_QUEUE_PATH, return_value=queue):
            result = await QualityAnalyzer().start(tmp_path)
        assert result.status == "analyzing"
        queue.enqueue_quality.assert_awaited_once_with(tmp_path)


class TestQualityAnalyzerSchedule:
    async def test_noop_when_cached(self, tmp_path: Path) -> None:
        _write_quality_report(tmp_path)
        queue = _queue(None)
        with patch(_QUEUE_PATH, return_value=queue):
            await QualityAnalyzer().schedule(tmp_path)
        queue.enqueue_quality.assert_not_awaited()

    async def test_noop_when_no_mcap(self, tmp_path: Path) -> None:
        queue = _queue(None)
        with patch(_QUEUE_PATH, return_value=queue):
            await QualityAnalyzer().schedule(tmp_path)
        queue.enqueue_quality.assert_not_awaited()

    async def test_enqueues_when_mcap_present(self, tmp_path: Path) -> None:
        (tmp_path / "rec.mcap").write_bytes(b"")
        queue = _queue(None)
        with patch(_QUEUE_PATH, return_value=queue):
            await QualityAnalyzer().schedule(tmp_path)
        queue.enqueue_quality.assert_awaited_once_with(tmp_path)


def test_get_quality_analyzer_returns_singleton() -> None:
    assert get_quality_analyzer() is get_quality_analyzer()
