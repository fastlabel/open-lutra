"""Tests for the LeRobot-export parts of the JobQueue."""

from pathlib import Path

import pytest

from app.features.jobs import service as jobs_service
from app.features.jobs.models import JobStatus, JobType, LeRobotExportJob
from app.features.jobs.service import JobQueue


@pytest.mark.asyncio
async def test_enqueue_lerobot_export_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    def fake_export(source_paths, output_dir, on_progress):
        on_progress("convert", 0, 1)
        calls.append((source_paths, output_dir))

    monkeypatch.setattr(jobs_service, "_run_export_dataset", fake_export)

    queue = JobQueue()
    await queue.start()
    try:
        out = tmp_path / "_lerobot_exports" / "ds"
        job = await queue.enqueue_lerobot_export(source_dirs=[tmp_path / "rec1"], output_dir=out)
        assert isinstance(job, LeRobotExportJob)
        assert job.type == JobType.LEROBOT_EXPORT
        finished = await queue.wait_for_completion(job.job_id)
        assert finished is not None
        assert finished.status == JobStatus.COMPLETED
        assert calls == [([tmp_path / "rec1"], out)]
    finally:
        await queue.shutdown()


@pytest.mark.asyncio
async def test_enqueue_lerobot_export_dedupes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    started = threading.Event()
    release = threading.Event()

    def fake_export(*_args, **_kwargs):
        # Block (in the worker thread) so the first job stays active while we
        # enqueue the duplicate.
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(jobs_service, "_run_export_dataset", fake_export)

    queue = JobQueue()
    await queue.start()
    try:
        out = tmp_path / "_lerobot_exports" / "ds"
        job1 = await queue.enqueue_lerobot_export(source_dirs=[tmp_path / "r"], output_dir=out)
        await __import__("asyncio").to_thread(started.wait, 5)
        job2 = await queue.enqueue_lerobot_export(source_dirs=[tmp_path / "r"], output_dir=out)
        assert job1.job_id == job2.job_id  # same destination -> deduped
        release.set()
        await queue.wait_for_completion(job1.job_id)
    finally:
        await queue.shutdown()
