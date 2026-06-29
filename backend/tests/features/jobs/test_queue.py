"""Tests for the generic JobQueue infrastructure and the media/quality/timeline runs.

Validation / upload / LeRobot-export specifics live in their own job test modules.
This covers enqueue dedup, lookups, the SSE subscription, the worker loop (dispatch,
failure handling, cancellation, history trimming) and the run methods whose underlying
MCAP work is mocked.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.features.jobs import service as jobs_service
from app.features.jobs.models import GenerateMediaJob, Job, JobStatus, JobType, QualityJob, TimelineJob
from app.features.jobs.service import EVENT_JOB_ADDED, JobQueue


class TestEnqueue:
    async def test_enqueue_generate_media(self, tmp_path: Path) -> None:
        queue = JobQueue()
        job = await queue.enqueue_generate_media(tmp_path)
        assert isinstance(job, GenerateMediaJob)
        assert job.type == JobType.MEDIA
        assert job.status == JobStatus.QUEUED
        active = queue.get_active_media_job(tmp_path)
        assert active is not None and active.job_id == job.job_id
        # Re-enqueue returns the existing job.
        assert (await queue.enqueue_generate_media(tmp_path)).job_id == job.job_id

    async def test_enqueue_quality(self, tmp_path: Path) -> None:
        queue = JobQueue()
        job = await queue.enqueue_quality(tmp_path)
        assert isinstance(job, QualityJob)
        active = queue.get_active_quality_job(tmp_path)
        assert active is not None and active.job_id == job.job_id
        assert (await queue.enqueue_quality(tmp_path)).job_id == job.job_id

    async def test_enqueue_timeline(self, tmp_path: Path) -> None:
        queue = JobQueue()
        job = await queue.enqueue_timeline(tmp_path)
        assert isinstance(job, TimelineJob)
        active = queue.get_active_timeline_job(tmp_path)
        assert active is not None and active.job_id == job.job_id
        assert (await queue.enqueue_timeline(tmp_path)).job_id == job.job_id


class TestLookups:
    async def test_get_job(self, tmp_path: Path) -> None:
        queue = JobQueue()
        job = await queue.enqueue_quality(tmp_path)
        assert queue.get_job(job.job_id) is job
        assert queue.get_job("missing") is None

    async def test_wait_for_completion_unknown_job(self) -> None:
        queue = JobQueue()
        assert await queue.wait_for_completion("missing") is None

    async def test_wait_for_completion_already_finished(self, tmp_path: Path) -> None:
        queue = JobQueue()
        job = await queue.enqueue_quality(tmp_path)
        job.status = JobStatus.COMPLETED
        assert await queue.wait_for_completion(job.job_id) is job

    async def test_list_jobs_combines_active_and_history(self, tmp_path: Path) -> None:
        queue = JobQueue()
        active = await queue.enqueue_quality(tmp_path)
        done = await queue.enqueue_timeline(tmp_path / "other")
        done.status = JobStatus.COMPLETED
        queue._history.append(done)
        jobs = queue.list_jobs()
        assert active in jobs and done in jobs


class TestSubscribe:
    async def test_yields_snapshot_then_events(self, tmp_path: Path) -> None:
        queue = JobQueue()
        await queue.enqueue_quality(tmp_path)
        agen = queue.subscribe()
        snapshot = await agen.__anext__()
        assert snapshot.event == "queue_snapshot"

        job = await queue.enqueue_timeline(tmp_path / "x")
        await queue._broadcast(EVENT_JOB_ADDED, job)
        event = await agen.__anext__()
        assert event.event == EVENT_JOB_ADDED

        await agen.aclose()
        assert not queue._subscribers


class TestWorker:
    async def test_dispatches_each_job_type(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        queue = JobQueue()
        for name in (
            "_run_generate_media",
            "_run_quality",
            "_run_timeline",
            "_run_validation",
            "_run_upload",
            "_run_lerobot_export",
        ):
            monkeypatch.setattr(queue, name, AsyncMock())

        await queue.start()
        try:
            jobs = [
                await queue.enqueue_generate_media(tmp_path / "m"),
                await queue.enqueue_quality(tmp_path / "q"),
                await queue.enqueue_timeline(tmp_path / "t"),
                await queue.enqueue_validation(tmp_path / "v"),
                await queue.enqueue_upload(tmp_path / "u"),
                await queue.enqueue_lerobot_export(source_dirs=[tmp_path / "s"], output_dir=tmp_path / "ds"),
            ]
            for job in jobs:
                finished = await queue.wait_for_completion(job.job_id)
                assert finished is not None and finished.status == JobStatus.COMPLETED
        finally:
            await queue.shutdown()

    async def test_marks_failed_on_exception(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        queue = JobQueue()
        monkeypatch.setattr(queue, "_run_quality", AsyncMock(side_effect=RuntimeError("kaboom")))
        await queue.start()
        try:
            job = await queue.enqueue_quality(tmp_path)
            finished = await queue.wait_for_completion(job.job_id)
            assert finished is not None
            assert finished.status == JobStatus.FAILED
            assert finished.error == "kaboom"
        finally:
            await queue.shutdown()

    async def test_worker_survives_unhandled_execute_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        queue = JobQueue()
        real_execute = queue._execute
        seen: list[str] = []

        async def flaky_execute(job: Job) -> None:
            seen.append(job.job_id)
            if len(seen) == 1:
                raise RuntimeError("boom")  # leaks to the worker loop
            await real_execute(job)

        monkeypatch.setattr(queue, "_execute", flaky_execute)
        monkeypatch.setattr(queue, "_run_quality", AsyncMock())

        await queue.start()
        try:
            await queue.enqueue_quality(tmp_path / "first")
            second = await queue.enqueue_quality(tmp_path / "second")
            finished = await queue.wait_for_completion(second.job_id)
            assert finished is not None and finished.status == JobStatus.COMPLETED
        finally:
            await queue.shutdown()

    async def test_worker_propagates_cancellation_during_execute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        queue = JobQueue()
        entered = asyncio.Event()

        async def hang(_job: Job) -> None:
            entered.set()
            await asyncio.sleep(3600)

        monkeypatch.setattr(queue, "_execute", hang)
        await queue.start()
        await queue.enqueue_quality(tmp_path)
        await asyncio.wait_for(entered.wait(), timeout=5)

        await queue.shutdown()
        task = queue._worker_task
        assert task is not None and task.done()

    async def test_history_trimmed_to_max(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(jobs_service, "_MAX_HISTORY", 2)
        queue = JobQueue()
        monkeypatch.setattr(queue, "_run_quality", AsyncMock())

        await queue.start()
        try:
            last: QualityJob | None = None
            for i in range(4):
                last = await queue.enqueue_quality(tmp_path / f"rec{i}")
            assert last is not None
            await queue.wait_for_completion(last.job_id)
            assert len(queue._history) == 2
        finally:
            await queue.shutdown()


class TestRunGenerateMedia:
    async def test_skips_when_mp4_exists(self, tmp_path: Path) -> None:
        (tmp_path / "observation.images.cam.mp4").write_bytes(b"")
        queue = JobQueue()
        job = await queue.enqueue_generate_media(tmp_path)
        await queue._run_generate_media(job)
        assert job.progress.step == "ready"

    async def test_raises_when_no_mcap(self, tmp_path: Path) -> None:
        queue = JobQueue()
        job = await queue.enqueue_generate_media(tmp_path)
        with pytest.raises(FileNotFoundError):
            await queue._run_generate_media(job)

    async def test_runs_conversion_and_reports_progress(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "rec.mcap").write_bytes(b"")
        seen: list[Path] = []

        def fake_convert(target: Path, on_progress: Callable[[str, int, int], None]) -> None:
            on_progress("mp4", 1, 2)  # exercise the progress callback hop
            seen.append(target)

        monkeypatch.setattr(jobs_service, "_run_convert_mcap", fake_convert)
        queue = JobQueue()
        job = await queue.enqueue_generate_media(tmp_path)
        await queue._run_generate_media(job)
        assert seen == [tmp_path]
        assert job.progress.step == "mp4"


class TestRunQuality:
    async def test_skips_when_cached(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.features.analysis.mcap_analyzer.load_report", lambda _t: MagicMock())
        queue = JobQueue()
        job = await queue.enqueue_quality(tmp_path)
        await queue._run_quality(job)
        assert job.progress.step == "ready"

    async def test_raises_when_no_mcap(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.features.analysis.mcap_analyzer.load_report", lambda _t: None)
        queue = JobQueue()
        job = await queue.enqueue_quality(tmp_path)
        with pytest.raises(FileNotFoundError):
            await queue._run_quality(job)

    async def test_runs_analysis(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "rec.mcap").write_bytes(b"")
        called: list[Path] = []
        monkeypatch.setattr("app.features.analysis.mcap_analyzer.load_report", lambda _t: None)
        monkeypatch.setattr("app.features.analysis.mcap_analyzer.analyze_and_save", called.append)
        queue = JobQueue()
        job = await queue.enqueue_quality(tmp_path)
        await queue._run_quality(job)
        assert called == [tmp_path]
        assert job.progress.step == "analyze"


class TestRunTimeline:
    async def test_skips_when_cached(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.features.analysis.timeline_analyzer.load_timeline", lambda _t: MagicMock())
        queue = JobQueue()
        job = await queue.enqueue_timeline(tmp_path)
        await queue._run_timeline(job)
        assert job.progress.step == "ready"

    async def test_raises_when_no_mcap(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.features.analysis.timeline_analyzer.load_timeline", lambda _t: None)
        queue = JobQueue()
        job = await queue.enqueue_timeline(tmp_path)
        with pytest.raises(FileNotFoundError):
            await queue._run_timeline(job)

    async def test_runs_build(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "rec.mcap").write_bytes(b"")
        called: list[Path] = []
        monkeypatch.setattr("app.features.analysis.timeline_analyzer.load_timeline", lambda _t: None)
        monkeypatch.setattr("app.features.analysis.timeline_analyzer.build_and_save_timeline", called.append)
        queue = JobQueue()
        job = await queue.enqueue_timeline(tmp_path)
        await queue._run_timeline(job)
        assert called == [tmp_path]


def test_get_job_queue_raises_when_uninitialized() -> None:
    previous = jobs_service._job_queue
    jobs_service._job_queue = None
    try:
        with pytest.raises(HTTPException) as exc_info:
            jobs_service.get_job_queue()
        assert exc_info.value.status_code == 503
    finally:
        jobs_service._job_queue = previous
