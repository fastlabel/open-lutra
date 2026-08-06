"""Recording API endpoints."""

import asyncio
import logging
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

from fastapi import APIRouter, status

from app.dependencies import RecorderDep
from app.features.recording.models import RecorderError
from app.features.recording.schemas import (
    RecordingStartRequest,
    RecordingStartResponse,
    RecordingStatus,
    RecordingStopResponse,
)
from app.shared.log_manager import LogSeverity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recording", tags=["recording"])


@router.post(
    "/start",
    response_model=RecordingStartResponse,
    status_code=status.HTTP_200_OK,
    operation_id="startRecording",
    responses={
        409: {"description": "Already recording"},
        500: {"description": "Failed to start recording"},
    },
)
async def start_recording(
    recorder: RecorderDep,
    request: RecordingStartRequest = RecordingStartRequest(),
) -> RecordingStartResponse:
    """Start recording ROS2 topics."""
    output_path = recorder.start(
        topics=request.topics,
        qos_overrides=_get_qos_overrides(),
        task_name=request.task_name,
        metadata=request.metadata,
    )
    start_time = recorder.get_status().start_time
    if start_time is None:
        # get_status() detected that the recorder died right after start() and
        # reset the state (crash-at-startup race, e.g. on a full disk).
        raise RecorderError(
            "Recorder process exited immediately after starting; no recording is in progress. "
            "A full disk is the most common cause; check the backend logs for details."
        )

    # Notify the log panel that recording has started.
    topic_count = len(request.topics) if request.topics else 0
    _notify_log("info", f"Recording started ({topic_count} topics) -> {output_path.name}")

    return RecordingStartResponse(
        output_path=str(output_path),
        start_time=start_time,
    )


@router.post(
    "/stop",
    response_model=RecordingStopResponse,
    status_code=status.HTTP_200_OK,
    operation_id="stopRecording",
    responses={
        409: {"description": "Not currently recording"},
    },
)
async def stop_recording(recorder: RecorderDep) -> RecordingStopResponse:
    """Stop the recording and kick off quality analysis in the background."""
    result = recorder.stop()

    duration = (result.end_time - result.start_time).total_seconds()

    _notify_log("info", f"Recording stopped ({duration:.1f}s) -> {result.output_path.name}")

    _spawn_background(_run_post_recording_analysis(result.output_path))

    return RecordingStopResponse(
        output_path=str(result.output_path),
        start_time=result.start_time,
        end_time=result.end_time,
        duration_sec=duration,
    )


@router.get(
    "/status",
    response_model=RecordingStatus,
    status_code=status.HTTP_200_OK,
    operation_id="getRecordingStatus",
)
async def get_recording_status(recorder: RecorderDep) -> RecordingStatus:
    """Return the current recording status."""
    recorder_status = recorder.get_status()

    return RecordingStatus(
        is_recording=recorder_status.is_recording,
        output_path=str(recorder_status.output_path) if recorder_status.output_path else None,
        start_time=recorder_status.start_time,
        elapsed_sec=recorder_status.elapsed_sec,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _notify_log(severity: LogSeverity, message: str) -> None:  # pragma: no cover
    """Add a message to LogManager.

    Silently skips when LogManager has not been initialized.
    """
    try:
        from app.shared.log_manager import get_log_manager

        get_log_manager().add(severity, message)
    except Exception as e:
        # Do not block the recording flow if LogManager is not initialized (early startup / tests).
        logger.debug("Skipping log add because LogManager is not initialized: %s", e)


def _get_qos_overrides() -> dict[str, str] | None:  # pragma: no cover
    """Fetch QoS information for subscribed topics from TopicMonitorService.

    Returns:
        Mapping of topic name -> reliability ("reliable"/"best_effort").
        Returns None when no information can be retrieved.
    """
    try:
        from app.dependencies import get_monitor

        monitor = get_monitor()
        stats = monitor.get_topic_stats()
        overrides: dict[str, str] = {}
        for s in stats:
            if s.qos_reliability:
                overrides[s.name] = s.qos_reliability.lower()
        if overrides:
            logger.info("Resolved QoS overrides: %s", overrides)
        return overrides if overrides else None
    except Exception as e:
        logger.warning("Failed to fetch QoS info (recording continues with default QoS): %s", e)
        return None


_background_tasks: set[asyncio.Task[None]] = set()


def _spawn_background(coro: Coroutine[Any, Any, None]) -> None:
    """Launch a coroutine as a background task (keeping a strong reference to prevent GC)."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _run_post_recording_analysis(output_path: Path) -> None:  # pragma: no cover
    """Schedule quality analysis followed by validation after recording stops.

    Both are placed on the job queue so that when the frontend hits
    GET /api/validation or GET /api/analysis/quality it can observe the
    "analyzing" state. JobQueue runs FIFO on a single worker, so the
    quality job always finishes before validation (which takes
    quality_report.json as input).
    """
    from app.features.analysis.quality_analyzer import get_quality_analyzer
    from app.features.validation.service import get_validation_service

    # Wait briefly for the MCAP file to be flushed.
    await asyncio.sleep(2.0)

    try:
        await get_quality_analyzer().schedule(output_path)
        _notify_log("info", f"Quality analysis started -> {output_path.name}")
    except Exception as e:
        logger.warning("Failed to schedule quality analysis: %s - %s", output_path, e)
        _notify_log("warning", f"Failed to start quality analysis: {e}")
        return

    try:
        await get_validation_service().schedule(output_path)
        _notify_log("info", f"Validation queued -> {output_path.name}")
    except Exception as e:
        logger.warning("Failed to schedule validation: %s - %s", output_path, e)
        _notify_log("warning", f"Failed to queue validation: {e}")
