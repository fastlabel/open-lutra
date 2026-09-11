"""Topic monitoring API endpoints (REST + SSE)."""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.dependencies import MonitorDep
from app.features.topics.schemas import (
    LatestMessageResponse,
    LiveToggleResponse,
    SubscriptionRequest,
    SubscriptionResponse,
    TopicsResponse,
)
from app.features.topics.stream import TopicStreamDiffer
from app.shared.log_manager import get_log_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/topics", tags=["topics"])


@router.get("", response_model=TopicsResponse, operation_id="getTopics")
async def list_topics(monitor: MonitorDep) -> TopicsResponse:
    """List statistics for all topics."""
    return TopicsResponse(
        topics=monitor.get_topic_stats(),
        discovered_topics=monitor.get_discovered_topics(),
    )


@router.get("/message", response_model=LatestMessageResponse, operation_id="getTopicMessage")
async def get_latest_message(
    monitor: MonitorDep,
    topic: str = Query(..., description="Topic name (e.g. /joint_states)"),
) -> LatestMessageResponse:
    """Return the latest message data for the given topic.

    On-demand capture mode: the first request only raises a flag and returns
    null; the next received message populates ``latest_message``. Clients
    re-fetch via ``refetchInterval`` to pick up the actual data. The contents
    of ``message`` depend on the ROS message type (``msg_type``) and the
    structure varies dynamically.
    """
    return LatestMessageResponse(message=monitor.get_latest_message(topic))


@router.get("/image/stream", operation_id="streamTopicImage")  # pragma: no cover
async def stream_topic_image(
    request: Request,
    monitor: MonitorDep,
    topic: str = Query(..., description="Image topic name"),
) -> StreamingResponse:
    """MJPEG stream: deliver an image topic in real time.

    Streams at 30fps while in Live mode, and 2fps otherwise.
    """

    async def generate() -> AsyncGenerator[bytes, None]:
        while True:
            if await request.is_disconnected():
                break
            raw = monitor.get_live_raw_image(topic)
            if raw:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(raw)).encode() + b"\r\n\r\n" + raw + b"\r\n"
                )
            # Live mode: 30fps, otherwise 2fps
            is_live = monitor.is_live(topic)
            await asyncio.sleep(1 / 30 if is_live else 0.5)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post(
    "/live/start",
    response_model=LiveToggleResponse,
    status_code=status.HTTP_200_OK,
    operation_id="startLive",
)  # pragma: no cover
async def start_live(
    monitor: MonitorDep,
    topic: str = Query(..., description="Target topic for Live mode"),
) -> LiveToggleResponse:
    """Start Live mode for the given topic."""
    ok = monitor.start_live(topic)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return LiveToggleResponse(status="started", topic=topic)


@router.post(
    "/live/stop",
    response_model=LiveToggleResponse,
    status_code=status.HTTP_200_OK,
    operation_id="stopLive",
)  # pragma: no cover
async def stop_live(
    monitor: MonitorDep,
    topic: str = Query(..., description="Target topic for Live mode"),
) -> LiveToggleResponse:
    """Stop Live mode."""
    monitor.stop_live(topic)
    return LiveToggleResponse(status="stopped", topic=topic)


@router.get("/live/stream", operation_id="streamLivePositions")  # pragma: no cover
async def stream_live_positions(
    request: Request,
    monitor: MonitorDep,
    topic: str = Query(..., description="Sensor topic name"),
) -> StreamingResponse:
    """SSE stream: deliver sensor positions captured in Live mode at 30fps."""

    async def generate() -> AsyncGenerator[str, None]:
        while True:
            if await request.is_disconnected():
                break
            result = monitor.get_live_positions(topic)
            if result is not None:
                yield f"data: {json.dumps(result)}\n\n"
            await asyncio.sleep(1 / 30)  # 30fps

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/reset-baseline", status_code=status.HTTP_204_NO_CONTENT, operation_id="resetBaseline")
async def reset_baseline(monitor: MonitorDep) -> None:  # pragma: no cover
    """Reset baseline Hz and quality metrics for all topics."""
    monitor.reset_baseline()


@router.post("/pause", status_code=status.HTTP_204_NO_CONTENT, operation_id="pauseMonitor")
async def pause_monitor(monitor: MonitorDep) -> None:  # pragma: no cover
    """Pause real-time monitoring."""
    monitor.pause()


@router.post("/resume", status_code=status.HTTP_204_NO_CONTENT, operation_id="resumeMonitor")
async def resume_monitor(monitor: MonitorDep) -> None:  # pragma: no cover
    """Resume real-time monitoring."""
    monitor.resume()


@router.put("/subscriptions", response_model=SubscriptionResponse, operation_id="updateSubscriptions")
async def update_subscriptions(
    monitor: MonitorDep,
    request: SubscriptionRequest,
) -> SubscriptionResponse:
    """Update the set of subscribed topics being monitored."""
    subscribed = monitor.update_subscriptions(request.topics)
    return SubscriptionResponse(subscribed=subscribed)


@router.get("/stream", operation_id="topicStream")
async def topic_stream(request: Request, monitor: MonitorDep) -> StreamingResponse:  # pragma: no cover
    """SSE stream for real-time topic monitoring.

    Event types:
      - topic_stats: rows that changed since the previous tick (1Hz; the
        first event on a connection carries every row)
      - log: new log entries (as they occur)
    """
    log_manager = get_log_manager()

    async def event_generator() -> AsyncGenerator[str, None]:
        last_log_id = 0
        differ = TopicStreamDiffer()

        while True:
            if await request.is_disconnected():
                break

            # Send subscribed + discovered topics together (once per second);
            # only rows that changed since the previous tick go on the wire.
            changed = differ.next_changed(monitor.get_topic_stats(), monitor.get_discovered_topics())
            yield f"event: topic_stats\ndata: {json.dumps(changed)}\n\n"

            # Send any new logs that arrived since the last check.
            new_logs = log_manager.get_logs_since(last_log_id)
            for log_entry in new_logs:
                yield f"event: log\ndata: {log_entry.model_dump_json()}\n\n"
                last_log_id = log_entry.id

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
