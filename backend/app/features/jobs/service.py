"""Job queue service.

Runs jobs sequentially using `asyncio.Queue` and a single worker.
Broadcasts status change events to subscribers (SSE) via `asyncio.Queue`.

Job types:
  - `GenerateMediaJob`: MCAP -> MP4 + telemetry.json conversion
  - `QualityJob`:       quality_report.json generation
  - `TimelineJob`:      timeline_data.json generation
  - `ValidationJob`:    validation_result.json generation
  - `UploadJob`:        zip recording + ship to the configured upload destination
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, status

from app.features.jobs.models import (
    GenerateMediaJob,
    Job,
    JobProgress,
    JobStatus,
    JobType,
    QualityJob,
    TimelineJob,
    UploadJob,
    ValidationJob,
)
from app.features.jobs.schemas import JobChangeEvent, JobEvent, JobSchema, QueueSnapshotData, QueueSnapshotEvent

logger = logging.getLogger(__name__)

# Labels corresponding to `convert_mcap()` progress steps
_STEP_LABELS: dict[str, str] = {
    "classify": "Classifying topics",
    "read": "Reading messages",
    "mp4": "Generating MP4",
    "telemetry": "Generating telemetry.json",
}

# Event types used internally by JobQueue (must match the Literal in JobChangeEvent.event)
JobChangeEventName = Literal["job_added", "job_started", "job_progress", "job_completed", "job_failed"]
EVENT_QUEUE_SNAPSHOT: Literal["queue_snapshot"] = "queue_snapshot"
EVENT_JOB_ADDED: JobChangeEventName = "job_added"
EVENT_JOB_STARTED: JobChangeEventName = "job_started"
EVENT_JOB_PROGRESS: JobChangeEventName = "job_progress"
EVENT_JOB_COMPLETED: JobChangeEventName = "job_completed"
EVENT_JOB_FAILED: JobChangeEventName = "job_failed"

# Maximum number of completed jobs to retain as history
_MAX_HISTORY = 50


class JobQueue:
    """Async job queue.

    - Executes jobs sequentially with a single worker
    - Broadcasts progress and status changes to subscribers (SSE)
    - Prevents duplicate generation for the same folder via `_active_folders`
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}
        self._history: list[Job] = []
        # Per-job-type mapping of "active job for the same folder" (prevents duplicate execution)
        # folder path string -> job_id
        self._active_folders: dict[JobType, dict[str, str]] = {
            JobType.MEDIA: {},
            JobType.QUALITY: {},
            JobType.TIMELINE: {},
            JobType.VALIDATION: {},
            JobType.UPLOAD: {},
        }
        self._subscribers: set[asyncio.Queue[JobEvent]] = set()
        self._worker_task: asyncio.Task[None] | None = None
        # Event dict for completion notification (used by wait_for_completion)
        self._completion_events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the worker task."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._run_worker())
            logger.info("JobQueue worker started")

    async def shutdown(self) -> None:
        """Stop the worker task (on application shutdown)."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            logger.info("JobQueue worker stopped")

    async def enqueue_generate_media(self, folder: Path) -> Job:
        """Enqueue an MP4 + telemetry.json generation job.

        If an active job already exists for the same folder, return it (prevents duplicate generation).

        Args:
            folder: Absolute path of the recording directory.

        Returns:
            The enqueued (or existing) Job.
        """
        async with self._lock:
            existing_id = self._active_folders[JobType.MEDIA].get(str(folder))
            if existing_id and existing_id in self._jobs:
                return self._jobs[existing_id]

            job = GenerateMediaJob(
                job_id=f"gen_{uuid.uuid4().hex[:12]}",
                type=JobType.MEDIA,
                folder=folder.name,
                progress=JobProgress(step="queued", step_label="Waiting", current=0, total=1),
                target_path=folder,
            )
            self._register_active(JobType.MEDIA, folder, job)

        await self._queue.put(job)
        await self._broadcast(EVENT_JOB_ADDED, job)
        logger.info("GenerateMediaJob added: %s (%s)", job.job_id, folder.name)
        return job

    async def enqueue_quality(self, folder: Path) -> QualityJob:
        """Enqueue a quality analysis job.

        If an active job already exists for the same folder, return it (prevents duplicate execution).
        """
        async with self._lock:
            existing_id = self._active_folders[JobType.QUALITY].get(str(folder))
            if existing_id and existing_id in self._jobs:
                existing = self._jobs[existing_id]
                if isinstance(existing, QualityJob):
                    return existing

            job = QualityJob(
                job_id=f"qua_{uuid.uuid4().hex[:12]}",
                type=JobType.QUALITY,
                folder=folder.name,
                progress=JobProgress(step="queued", step_label="Waiting", current=0, total=1),
                target_path=folder,
            )
            self._register_active(JobType.QUALITY, folder, job)

        await self._queue.put(job)
        await self._broadcast(EVENT_JOB_ADDED, job)
        logger.info("QualityJob added: %s (%s)", job.job_id, folder.name)
        return job

    async def enqueue_validation(self, folder: Path) -> ValidationJob:
        """Enqueue a validation execution job.

        If an active job already exists for the same folder, return it (prevents duplicate execution).
        """
        async with self._lock:
            existing_id = self._active_folders[JobType.VALIDATION].get(str(folder))
            if existing_id and existing_id in self._jobs:
                existing = self._jobs[existing_id]
                if isinstance(existing, ValidationJob):
                    return existing

            job = ValidationJob(
                job_id=f"val_{uuid.uuid4().hex[:12]}",
                type=JobType.VALIDATION,
                folder=folder.name,
                progress=JobProgress(step="queued", step_label="Waiting", current=0, total=1),
                target_path=folder,
            )
            self._register_active(JobType.VALIDATION, folder, job)

        await self._queue.put(job)
        await self._broadcast(EVENT_JOB_ADDED, job)
        logger.info("ValidationJob added: %s (%s)", job.job_id, folder.name)
        return job

    async def enqueue_upload(self, folder: Path) -> UploadJob:
        """Enqueue an upload job (zip + ship to the configured destination).

        If an active job already exists for the same folder, return it (prevents
        duplicate execution).
        """
        async with self._lock:
            existing_id = self._active_folders[JobType.UPLOAD].get(str(folder))
            if existing_id and existing_id in self._jobs:
                existing = self._jobs[existing_id]
                if isinstance(existing, UploadJob):
                    return existing

            job = UploadJob(
                job_id=f"upl_{uuid.uuid4().hex[:12]}",
                type=JobType.UPLOAD,
                folder=folder.name,
                progress=JobProgress(step="queued", step_label="Waiting", current=0, total=1),
                target_path=folder,
            )
            self._register_active(JobType.UPLOAD, folder, job)

        await self._queue.put(job)
        await self._broadcast(EVENT_JOB_ADDED, job)
        logger.info("UploadJob added: %s (%s)", job.job_id, folder.name)
        return job

    async def enqueue_timeline(self, folder: Path) -> TimelineJob:
        """Enqueue a timeline data generation job.

        If an active job already exists for the same folder, return it (prevents duplicate execution).
        """
        async with self._lock:
            existing_id = self._active_folders[JobType.TIMELINE].get(str(folder))
            if existing_id and existing_id in self._jobs:
                existing = self._jobs[existing_id]
                if isinstance(existing, TimelineJob):
                    return existing

            job = TimelineJob(
                job_id=f"tml_{uuid.uuid4().hex[:12]}",
                type=JobType.TIMELINE,
                folder=folder.name,
                progress=JobProgress(step="queued", step_label="Waiting", current=0, total=1),
                target_path=folder,
            )
            self._register_active(JobType.TIMELINE, folder, job)

        await self._queue.put(job)
        await self._broadcast(EVENT_JOB_ADDED, job)
        logger.info("TimelineJob added: %s (%s)", job.job_id, folder.name)
        return job

    async def wait_for_completion(self, job_id: str) -> Job | None:
        """Wait for the specified job to complete or fail.

        Args:
            job_id: ID of the job to wait for.

        Returns:
            The completed/failed job. Returns None if job_id does not exist.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            event = self._completion_events.get(job_id)

        if job is None:
            return None
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
            return job
        if event is None:  # pragma: no cover
            return job

        await event.wait()
        return self._jobs.get(job_id)

    def get_job(self, job_id: str) -> Job | None:
        """Look up a job by its ID."""
        return self._jobs.get(job_id)

    def get_active_media_job(self, folder: Path) -> Job | None:
        """Return the in-progress/queued media job for the specified folder."""
        return self._get_active_job(JobType.MEDIA, folder)

    def get_active_quality_job(self, folder: Path) -> Job | None:
        """Return the in-progress/queued quality job for the specified folder."""
        return self._get_active_job(JobType.QUALITY, folder)

    def get_active_timeline_job(self, folder: Path) -> Job | None:
        """Return the in-progress/queued timeline job for the specified folder."""
        return self._get_active_job(JobType.TIMELINE, folder)

    def get_active_validation_job(self, folder: Path) -> Job | None:
        """Return the in-progress/queued validation job for the specified folder."""
        return self._get_active_job(JobType.VALIDATION, folder)

    def get_active_upload_job(self, folder: Path) -> Job | None:
        """Return the in-progress/queued upload job for the specified folder."""
        return self._get_active_job(JobType.UPLOAD, folder)

    def list_jobs(self) -> list[Job]:
        """Return active jobs combined with recent history."""
        active = [j for j in self._jobs.values() if j.status in (JobStatus.QUEUED, JobStatus.RUNNING)]
        return active + list(self._history)

    async def subscribe(self) -> AsyncIterator[JobEvent]:
        """Subscription generator for SSE.

        Sends the current queue snapshot on connect, then streams status change events.
        """
        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        self._subscribers.add(queue)

        try:
            # Initial snapshot
            yield QueueSnapshotEvent(
                event="queue_snapshot",
                data=QueueSnapshotData(jobs=[JobSchema.from_job(j) for j in self.list_jobs()]),
            )
            # Stream status change events
            while True:
                event = await queue.get()
                yield event
        finally:
            self._subscribers.discard(queue)

    def _register_active(self, job_type: JobType, folder: Path, job: Job) -> None:
        """Register the active mapping along with jobs/completion_events in one shot (call inside the lock)."""
        self._active_folders[job_type][str(folder)] = job.job_id
        self._jobs[job.job_id] = job
        self._completion_events[job.job_id] = asyncio.Event()

    def _get_active_job(self, job_type: JobType, folder: Path) -> Job | None:
        job_id = self._active_folders[job_type].get(str(folder))
        if job_id:
            return self._jobs.get(job_id)
        return None

    async def _run_worker(self) -> None:
        """Worker loop: pull jobs from the queue and execute them."""
        while True:
            job = await self._queue.get()
            try:
                await self._execute(job)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # Do not stop the worker even if an unexpected exception leaks
                logger.exception("Unhandled exception in worker: %s", e)
            finally:
                self._queue.task_done()

    async def _execute(self, job: Job) -> None:
        """Execute a single job."""
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        await self._broadcast(EVENT_JOB_STARTED, job)
        logger.info("Job started: %s (%s, %s)", job.job_id, job.type.value, job.folder)

        try:
            if isinstance(job, GenerateMediaJob):
                await self._run_generate_media(job)
            elif isinstance(job, QualityJob):
                await self._run_quality(job)
            elif isinstance(job, TimelineJob):
                await self._run_timeline(job)
            elif isinstance(job, ValidationJob):
                await self._run_validation(job)
            elif isinstance(job, UploadJob):
                await self._run_upload(job)
            else:  # pragma: no cover
                raise ValueError(f"Unknown job type: {job.type}")

            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.now(timezone.utc)
            await self._broadcast(EVENT_JOB_COMPLETED, job)
            logger.info("Job completed: %s", job.job_id)
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e) or e.__class__.__name__
            job.finished_at = datetime.now(timezone.utc)
            await self._broadcast(EVENT_JOB_FAILED, job)
            logger.error("Job failed: %s - %s", job.job_id, e)
        finally:
            # On completion/failure, release the active mapping and push to history
            async with self._lock:
                target_path = getattr(job, "target_path", None)
                if target_path is not None:
                    active_map = self._active_folders.get(job.type)
                    if active_map is not None and active_map.get(str(target_path)) == job.job_id:
                        active_map.pop(str(target_path), None)
                # Push to history (drop old entries)
                self._history.insert(0, job)
                if len(self._history) > _MAX_HISTORY:
                    removed = self._history[_MAX_HISTORY:]
                    self._history = self._history[:_MAX_HISTORY]
                    for r in removed:
                        self._jobs.pop(r.job_id, None)
                        self._completion_events.pop(r.job_id, None)
                # Signal the completion Event (releases wait_for_completion)
                event = self._completion_events.get(job.job_id)
                if event is not None:
                    event.set()

    async def _run_generate_media(self, job: GenerateMediaJob) -> None:
        """Call `convert_mcap()` and reflect its progress onto the Job."""
        target = job.target_path
        if target is None:  # pragma: no cover
            raise ValueError(f"GenerateMediaJob.target_path is not set: {job.job_id}")

        # Skip if MP4 has already been generated (prevents duplicate generation)
        if list(target.glob("*.mp4")):
            logger.info("Existing MP4 detected, skipping generation: %s", target.name)
            job.progress = JobProgress(step="ready", step_label="Already generated", current=1, total=1)
            await self._broadcast(EVENT_JOB_PROGRESS, job)
            return

        if not list(target.glob("*.mcap")):
            raise FileNotFoundError(f"MCAP file not found: {target.name}")

        loop = asyncio.get_running_loop()

        def on_progress(step: str, current: int, total: int) -> None:
            """Progress callback invoked from `convert_mcap()` (on a different thread).

            Hops back to the main loop to broadcast.
            """
            job.progress = JobProgress(
                step=step,
                step_label=_STEP_LABELS.get(step, step),
                current=current,
                total=max(total, 1),
            )
            # Safely dispatch the progress event onto the main loop
            asyncio.run_coroutine_threadsafe(
                self._broadcast(EVENT_JOB_PROGRESS, job),
                loop,
            )

        await asyncio.to_thread(_run_convert_mcap, target, on_progress)

    async def _run_quality(self, job: QualityJob) -> None:
        """Run quality analysis (`analyze_and_save`).

        Skip if already cached.
        Progress has only two stages, `analyzing` -> `done` (no fine-grained
        progress is emitted because MCAP is read in a single pass).
        """
        target = job.target_path
        if target is None:  # pragma: no cover
            raise ValueError(f"QualityJob.target_path is not set: {job.job_id}")

        from app.features.analysis.mcap_analyzer import analyze_and_save, load_report

        if load_report(target) is not None:
            logger.info("Existing quality_report.json detected, skipping generation: %s", target.name)
            job.progress = JobProgress(step="ready", step_label="Already generated", current=1, total=1)
            await self._broadcast(EVENT_JOB_PROGRESS, job)
            return

        if not list(target.glob("*.mcap")):
            raise FileNotFoundError(f"MCAP file not found: {target.name}")

        job.progress = JobProgress(step="analyze", step_label="Analyzing MCAP", current=0, total=1)
        await self._broadcast(EVENT_JOB_PROGRESS, job)

        await asyncio.to_thread(analyze_and_save, target)

    async def _run_validation(self, job: ValidationJob) -> None:
        """Run all validators with ValidationRunner and generate validation_result.json.

        - Skip if already cached
        - Fail if the QualityReport is missing (assumes quality analysis ran first)
        - Include task_name from the recording meta in the report
        """
        target = job.target_path
        if target is None:  # pragma: no cover
            raise ValueError(f"ValidationJob.target_path is not set: {job.job_id}")

        from app.features.analysis.mcap_analyzer import load_report as load_quality_report
        from app.features.recordings.meta import read_recording_meta
        from app.features.validation.cache import load_report as load_validation_report
        from app.features.validation.cache import save_report as save_validation_report
        from app.features.validation.runner import ValidationRunner
        from app.infra.mcap import find_mcap_files

        if load_validation_report(target) is not None:
            logger.info("Existing validation_result.json detected, skipping generation: %s", target.name)
            job.progress = JobProgress(step="ready", step_label="Already generated", current=1, total=1)
            await self._broadcast(EVENT_JOB_PROGRESS, job)
            return

        quality_report = load_quality_report(target)
        if quality_report is None:
            raise FileNotFoundError(
                f"Cannot run validation because the quality report (quality_report.json) has not been generated: {target.name}"
            )

        job.progress = JobProgress(step="validate", step_label="Running validation", current=0, total=1)
        await self._broadcast(EVENT_JOB_PROGRESS, job)

        meta = read_recording_meta(target)
        mcap_files = find_mcap_files(target)
        mcap_path = mcap_files[0] if mcap_files else None

        runner = ValidationRunner()
        report = await asyncio.to_thread(
            runner.run,
            quality_report,
            recording_dir=target,
            mcap_path=mcap_path,
            recording_meta=meta,
        )
        await asyncio.to_thread(save_validation_report, target, report)

    async def _run_upload(self, job: UploadJob) -> None:
        """Zip the recording folder and ship it to the configured destination.

        Persists `upload_state.json` at every stage (uploading -> uploaded /
        failed) so reloads mid-upload recover gracefully. Per issue #6, this
        path always overwrites (no skip-if-cached); duplicate dispatches are
        prevented one level up by `enqueue_upload`.
        """
        target = job.target_path
        if target is None:  # pragma: no cover
            raise ValueError(f"UploadJob.target_path is not set: {job.job_id}")

        from app.features.recordings.scanner import read_metadata_summary
        from app.features.upload.cache import save_state
        from app.features.upload.destinations import get_active_destination
        from app.features.upload.key_template import render_key
        from app.features.upload.models import UploadState
        from app.features.upload.progress import ThrottledProgress
        from app.features.upload.zip_builder import build_zip
        from app.settings import get_settings

        settings = get_settings()
        destination = get_active_destination(settings)
        err = destination.configuration_error()
        if err is not None:
            raise RuntimeError(err)
        # configuration_error() guarantees these are set; assert for the type checker.
        assert settings.s3_bucket is not None
        assert settings.s3_key_template is not None

        _, recording_start_ns, _, _ = read_metadata_summary(target)
        if recording_start_ns is None:
            raise FileNotFoundError(
                f"Cannot determine recording start time from metadata.yaml: {target.name}",
            )
        key = render_key(
            settings.s3_key_template,
            recording_name=target.name,
            recording_start_ns=recording_start_ns,
        )

        job.progress = JobProgress(step="zip", step_label="Building zip", current=0, total=1)
        await self._broadcast(EVENT_JOB_PROGRESS, job)
        zip_path = await asyncio.to_thread(build_zip, target)
        zip_size = zip_path.stat().st_size

        state = UploadState(
            status="uploading",
            destination=settings.s3_bucket,
            key=key,
            etag=None,
            size_bytes=zip_size,
            bytes_transferred=0,
            uploaded_at=None,
            error=None,
        )
        await asyncio.to_thread(save_state, target, state)

        loop = asyncio.get_running_loop()

        def on_progress(bytes_transferred: int) -> None:
            """Throttled progress callback invoked from boto3 worker threads."""
            state.bytes_transferred = bytes_transferred
            save_state(target, state)
            job.progress = JobProgress(
                step="upload",
                step_label="Uploading",
                current=bytes_transferred,
                total=max(zip_size, 1),
            )
            asyncio.run_coroutine_threadsafe(
                self._broadcast(EVENT_JOB_PROGRESS, job),
                loop,
            )

        throttled = ThrottledProgress(on_progress)

        try:
            result = await asyncio.to_thread(destination.upload, zip_path, key, throttled)
            throttled.close()
            final = state.model_copy(
                update={
                    "status": "uploaded",
                    "etag": result.etag,
                    "size_bytes": result.size_bytes,
                    "bytes_transferred": result.size_bytes,
                    "uploaded_at": datetime.now(timezone.utc),
                },
            )
            await asyncio.to_thread(save_state, target, final)
        except Exception as e:
            failed = state.model_copy(update={"status": "failed", "error": str(e) or e.__class__.__name__})
            await asyncio.to_thread(save_state, target, failed)
            raise

    async def _run_timeline(self, job: TimelineJob) -> None:
        """Run timeline data generation (`build_and_save_timeline`).

        Skip if already cached.
        """
        target = job.target_path
        if target is None:  # pragma: no cover
            raise ValueError(f"TimelineJob.target_path is not set: {job.job_id}")

        from app.features.analysis.timeline_analyzer import build_and_save_timeline, load_timeline

        if load_timeline(target) is not None:
            logger.info("Existing timeline_data.json detected, skipping generation: %s", target.name)
            job.progress = JobProgress(step="ready", step_label="Already generated", current=1, total=1)
            await self._broadcast(EVENT_JOB_PROGRESS, job)
            return

        if not list(target.glob("*.mcap")):
            raise FileNotFoundError(f"MCAP file not found: {target.name}")

        job.progress = JobProgress(step="analyze", step_label="Analyzing MCAP", current=0, total=1)
        await self._broadcast(EVENT_JOB_PROGRESS, job)

        await asyncio.to_thread(build_and_save_timeline, target)

    async def _broadcast(self, event: JobChangeEventName, job: Job) -> None:
        """Broadcast an event to all subscribers."""
        payload = JobChangeEvent(event=event, data=JobSchema.from_job(job))
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:  # pragma: no cover
                logger.warning("Subscriber queue is full, dropping event: %s", event)


def _run_convert_mcap(  # pragma: no cover
    target: Path,
    on_progress: Callable[[str, int, int], None],
) -> None:
    """Thin wrapper around `convert_mcap()` for `asyncio.to_thread`."""
    from app.features.media.mcap_converter import convert_mcap
    from app.features.media.video_generator import VIDEO_FPS

    convert_mcap(target, target, VIDEO_FPS, on_progress=on_progress)


_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """DI function that returns the JobQueue instance."""
    if _job_queue is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JobQueue service not initialized",
        )
    return _job_queue


def set_job_queue(queue: JobQueue) -> None:
    """Set the global JobQueue instance (call at application startup)."""
    global _job_queue
    _job_queue = queue
