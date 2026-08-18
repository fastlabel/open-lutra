"""Topic monitoring schemas."""

from typing import Any

from pydantic import BaseModel, Field

from app.shared.log_manager import LogEntry  # Log model is consolidated under shared/ for SSE reuse.

__all__ = [
    "DiscoveredTopic",
    "LatestMessageResponse",
    "LiveToggleResponse",
    "LogEntry",
    "LogsResponse",
    "SubscriptionRequest",
    "SubscriptionResponse",
    "TopicInfo",
    "TopicsResponse",
]


class TopicInfo(BaseModel):
    """Information about a monitored topic."""

    name: str
    msg_type: str
    actual_hz: float
    status: str
    message_count: int
    is_subscribed: bool
    baseline_hz: float | None
    baseline_fixed: bool
    loss_rate: float
    drop_count: int
    continuity_score: float
    qos_reliability: str


class DiscoveredTopic(BaseModel):
    """A topic discovered in the DDS domain that has not yet been subscribed."""

    name: str
    msg_type: str
    is_subscribed: bool


class TopicsResponse(BaseModel):
    """Response for GET /api/topics."""

    topics: list[TopicInfo]
    discovered_topics: list[DiscoveredTopic]


class LogsResponse(BaseModel):
    """Response for GET /api/topics/logs."""

    logs: list[LogEntry]
    total: int


class SubscriptionRequest(BaseModel):
    """Request body for PUT /api/topics/subscriptions."""

    topics: list[str] = Field(..., description="List of topic names to subscribe to")


class SubscriptionResponse(BaseModel):
    """Response for PUT /api/topics/subscriptions."""

    subscribed: list[str]


class LiveToggleResponse(BaseModel):
    """Response for POST /api/topics/live/start and POST /api/topics/live/stop."""

    status: str = Field(..., pattern=r"^(started|stopped)$", description="Result of the Live mode transition")
    topic: str = Field(..., description="Target topic name")


class LatestMessageResponse(BaseModel):
    """Response for GET /api/topics/message.

    Because capture is on-demand, `message` is null on the first request and
    before any message has been received. Clients should treat null as
    "waiting for the next message to arrive".
    """

    message: dict[str, Any] | None = Field(
        ..., description="ROS-message-type-dependent dict; null when no message has been received yet"
    )
