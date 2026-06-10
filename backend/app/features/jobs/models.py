"""Job models (domain definitions).

Represents the status, type, and progress of a Job handled by the job queue.
Kept separate from API schemas (schemas.py) as a domain model that does not depend on JSON serialization.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    """Job execution status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    """Job type.

    All heavy processing (MCAP I/O and ffmpeg) is classified by this enum and
    placed on the job queue. This provides:
      - Visibility of in-progress tasks in the StatusBar
      - Prevention of duplicate execution for the same folder
      - Sequential execution by a single worker to reduce I/O contention
    """

    MEDIA = "media"  # MP4 + telemetry.json generation
    QUALITY = "quality"  # quality_report.json generation
    TIMELINE = "timeline"  # timeline_data.json generation
    VALIDATION = "validation"  # validation_result.json generation
    LEROBOT_EXPORT = "lerobot_export"  # LeRobot v3.0 dataset export (spans multiple recordings)


@dataclass
class JobProgress:
    """Job progress information."""

    step: str = ""
    step_label: str = ""
    current: int = 0
    total: int = 1


@dataclass
class Job:
    """Job base class.

    Attributes:
        job_id: Unique job ID (URL-safe string).
        type: Job type (media / quality / timeline).
        folder: Target recording folder name.
        status: Execution status.
        progress: Progress information.
        error: Error message on failure.
        created_at: Time the job was added to the queue.
        started_at: Time the job started execution.
        finished_at: Time the job completed or failed.
    """

    job_id: str
    type: JobType
    folder: str
    status: JobStatus = JobStatus.QUEUED
    progress: JobProgress = field(default_factory=JobProgress)
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class GenerateMediaJob(Job):
    """MP4 + telemetry.json generation job.

    Backed by a single call to `convert_mcap()`.

    Attributes:
        target_path: Absolute path of the recording directory (used by the worker, not exposed via the API).
    """

    target_path: Path | None = None


@dataclass
class QualityJob(Job):
    """Quality analysis job.

    Calls `analyze_and_save()` to generate quality_report.json.
    """

    target_path: Path | None = None


@dataclass
class TimelineJob(Job):
    """Timeline data generation job.

    Calls `build_and_save_timeline()` to generate timeline_data.json.
    """

    target_path: Path | None = None


@dataclass
class ValidationJob(Job):
    """Validation execution job.

    Loads the QualityReport, runs all validators via ValidationRunner, and generates
    validation_result.json. Used in the auto-chain after recording stops or for manual re-runs.
    """

    target_path: Path | None = None


@dataclass
class LeRobotExportJob(Job):
    """LeRobot v3.0 dataset export job.

    Unlike the per-recording jobs, this one spans multiple source recordings and
    writes a single dataset directory.

    Attributes:
        target_path: Output dataset directory (also the dedup key, so the shared
            `_active_folders` release logic in JobQueue works unchanged).
        source_paths: Recording directories, each exported as one episode.

    The mapping comes from the active robot config's `lerobot_export` section,
    read when the job runs.
    """

    target_path: Path | None = None
    source_paths: list[Path] = field(default_factory=list)
