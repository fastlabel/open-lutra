"""Topic monitoring service.

Domain logic for real-time topic discovery, frequency monitoring, and gap
detection. Independent of rclpy; communicates with ROS2 through the
infrastructure layer (TopicSubscriber Protocol).
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from app.features.topics.models import GapRecord, TopicStats
from app.features.topics.schemas import (
    DiscoveredTopic,
    TopicInfo,
)
from app.shared.stamp import extract_stamp_sec

if TYPE_CHECKING:
    from app.shared.log_manager import LogManager

logger = logging.getLogger(__name__)

# ROS2 system topics excluded from discovery.
_SYSTEM_TOPICS = frozenset({"/parameter_events", "/rosout"})
_SYSTEM_TOPIC_PREFIXES = ("/events/",)


class TopicSubscriber(Protocol):
    """Interface to the rclpy node (implemented by the infrastructure layer)."""

    def discover_topics(self) -> list[tuple[str, list[str]]]:
        """Return the names and types of all topics on the DDS domain."""
        ...

    def subscribe_topic(
        self,
        topic_name: str,
        msg_type_str: str,
        callback: Callable[[str, Any], None],
    ) -> str | None:
        """Subscribe to a topic. Returns the QoS reliability string on success."""
        ...

    def unsubscribe_topic(self, topic_name: str) -> None:
        """Tear down the subscription for a topic."""
        ...

    def convert_message(self, msg: Any) -> dict[str, Any]:
        """Convert a ROS2 message into a dict."""
        ...


class TopicMonitorService:
    """Domain logic for topic monitoring (rclpy-independent).

    Communicates with the infrastructure layer through the TopicSubscriber
    Protocol to track message frequencies and detect data stalls. All public
    accessors are thread-safe.
    """

    def __init__(
        self,
        subscribed_topics: list[str],
        log_manager: LogManager,
        *,
        gap_threshold_sec: float = 3.0,
        resolve_expected_hz: Callable[[str], float | None] | None = None,
        stamp_quality: bool = False,
    ) -> None:
        # Guards _topic_stats / _subscribed_set / _discovered_topics, which the
        # rclpy thread (on_message, timers) and the API thread share. Never call
        # into the subscriber (rclpy / DDS) while holding it: those calls block
        # on DDS discovery, and every API request would stall behind them.
        self._lock = threading.Lock()
        self._subscriber: TopicSubscriber | None = None
        self._topic_stats: dict[str, TopicStats] = {}
        self._log_manager = log_manager
        self._subscribed_topic_names = set(subscribed_topics)
        self._subscribed_set: set[str] = set()
        self._discovered_topics: dict[str, str] = {}
        self._gap_threshold_sec = gap_threshold_sec
        self._resolve_expected_hz = resolve_expected_hz
        self._stamp_quality = stamp_quality

        self._paused = False

        self._log_manager.add("info", "Topic monitoring started")
        logger.info("TopicMonitorService initialized; monitoring %d topics", len(subscribed_topics))

    def set_subscriber(self, subscriber: TopicSubscriber) -> None:
        """Configure the infrastructure-layer subscriber (call once at startup)."""
        self._subscriber = subscriber

    def get_topic_stats(self) -> list[TopicInfo]:
        """Return statistics for every subscribed topic.

        Advances dynamic baseline learning and refreshes caches in bulk before
        producing the API response. Learning runs before the cache refresh so
        a freshly locked-in baseline feeds this tick's status / loss_rate.
        Used by: GET /api/topics, GET /api/topics/stream.
        """
        now = time.monotonic()
        with self._lock:
            for s in self._topic_stats.values():
                learned = s.maybe_learn_baseline(now)
                if learned is not None:
                    self._log_manager.add(
                        "info",
                        f"Baseline Hz for {s.name}: {learned:.0f}Hz (dynamic learning)",
                        s.name,
                    )
                    logger.info("Baseline Hz for %s: %.1f (dynamic learning)", s.name, learned)
                s.refresh_cache(now)
            return [s.to_api() for s in self._topic_stats.values()]

    def get_discovered_topics(self) -> list[DiscoveredTopic]:
        """Return topics that have been discovered but not yet subscribed.

        Used by: GET /api/topics, GET /api/topics/stream.
        """
        with self._lock:
            return [
                DiscoveredTopic(
                    name=name,
                    msg_type=msg_type,
                    is_subscribed=name in self._subscribed_set,
                )
                for name, msg_type in self._discovered_topics.items()
                if name not in self._subscribed_set
            ]

    def get_latest_message(self, topic_name: str) -> dict[str, Any] | None:
        """Return the latest message for the given topic.

        Does not affect the on_message hot path; instead, requests a single
        message capture on the next receipt (on-demand mode).
        Used by: GET /api/topics/message.
        """
        with self._lock:
            stats = self._topic_stats.get(topic_name)
            if stats is None:
                return None
            # Raise the capture flag (the next on_message will convert one message).
            stats._capture_next = True
            return stats.latest_message

    def get_live_raw_image(self, topic_name: str) -> bytes:
        """Return the latest raw frame bytes for an image topic (for MJPEG).

        Used by: GET /api/topics/image/stream.
        """
        with self._lock:
            stats = self._topic_stats.get(topic_name)
            if stats is None:
                return b""
            return stats._live_raw_image

    def is_live(self, topic_name: str) -> bool:
        """Return whether the given topic is currently in Live mode.

        Used by: GET /api/topics/image/stream.
        """
        with self._lock:
            stats = self._topic_stats.get(topic_name)
            return stats._live_mode if stats is not None else False

    def start_live(self, topic_name: str) -> bool:
        """Start Live mode for the given topic.

        Used by: POST /api/topics/live/start.
        """
        with self._lock:
            # Stop any existing Live session first.
            for stats in self._topic_stats.values():
                stats._live_mode = False
            target = self._topic_stats.get(topic_name)
            if target is None:
                return False
            target._live_mode = True
            target._live_raw_image = b""
            self._log_manager.add("info", f"{topic_name}: Live mode started", topic_name)
            return True

    def stop_live(self, topic_name: str) -> None:
        """Stop Live mode.

        Used by: POST /api/topics/live/stop.
        """
        with self._lock:
            stats = self._topic_stats.get(topic_name)
            if stats is None:
                return
            stats._live_mode = False
            self._log_manager.add("info", f"{topic_name}: Live mode stopped", topic_name)

    def get_live_positions(self, topic_name: str) -> dict[str, Any] | None:
        """Return the sensor position array captured while in Live mode.

        Used by: GET /api/topics/live/stream.
        """
        with self._lock:
            stats = self._topic_stats.get(topic_name)
            if stats is None or not stats._live_mode:
                return None
            if not stats._live_positions:
                return None
            return {
                "positions": stats._live_positions,
                "names": stats._live_joint_names,
            }

    def reset_baseline(self) -> None:
        """Reset dynamically learned baseline Hz values and quality metrics.

        Topics with a fixed baseline (from YAML config) keep their baseline Hz;
        only dynamically learned topics restart learning.
        Used by: POST /api/topics/reset-baseline.
        """
        with self._lock:
            for stats in self._topic_stats.values():
                if not stats.baseline_fixed:
                    stats.baseline_hz = None
                self._reset_stats_timing(stats)
            self._log_manager.add("info", "Baseline Hz reset (dynamically learned topics will restart learning)")
            logger.info("Baseline Hz reset (fixed baselines preserved)")

    def pause(self) -> None:
        """Pause real-time monitoring.

        Skips on_message callback processing to reduce CPU load. DDS
        subscriptions are kept open, so resume restarts immediately.
        Used by: POST /api/topics/pause.
        """
        self._paused = True
        self._log_manager.add("info", "Real-time monitoring paused")
        logger.info("Real-time monitoring paused")

    def resume(self) -> None:
        """Resume real-time monitoring.

        Resets timing-related metrics so that elapsed pause time does not
        produce false missing-rate or gap detections (baseline_hz is kept).
        Used by: POST /api/topics/resume.
        """
        with self._lock:
            for stats in self._topic_stats.values():
                self._reset_stats_timing(stats)
        self._paused = False
        self._log_manager.add("info", "Real-time monitoring resumed")
        logger.info("Real-time monitoring resumed")

    def update_subscriptions(self, topics: list[str]) -> list[str]:
        """Dynamically update the set of subscribed topics.

        Used by: PUT /api/topics/subscriptions.

        Returns:
            List of topic names currently subscribed.
        """
        new_set = set(topics)

        with self._lock:
            # Drop the stats of deselected topics first so that messages
            # arriving before the DDS teardown below are ignored.
            to_remove = sorted(name for name in self._topic_stats if name not in new_set)
            for name in to_remove:
                self._subscribed_set.discard(name)
                self._topic_stats.pop(name)
            self._subscribed_topic_names = new_set
            reserved = self._reserve_subscriptions()

        for name in to_remove:
            if self._subscriber is not None:
                self._subscriber.unsubscribe_topic(name)
            self._log_manager.add("info", f"Unsubscribed from {name}", name)
            logger.info("Unsubscribed from %s", name)

        self._subscribe_reserved(reserved)

        with self._lock:
            return sorted(self._subscribed_set)

    def on_discover_tick(self) -> None:
        """Discover all topics on the DDS domain and subscribe to new ones."""
        if self._subscriber is None:
            return
        topic_names_and_types = self._subscriber.discover_topics()

        with self._lock:
            for name, types in topic_names_and_types:
                if name in _SYSTEM_TOPICS or any(name.startswith(p) for p in _SYSTEM_TOPIC_PREFIXES):
                    continue
                self._discovered_topics[name] = types[0] if types else "unknown"
            reserved = self._reserve_subscriptions()

        self._subscribe_reserved(reserved)

    def on_gap_check_tick(self) -> None:
        """Periodically check for topics that have stalled."""
        now = time.monotonic()
        with self._lock:
            for stats in self._topic_stats.values():
                if stats.message_count == 0 or stats._last_msg_time == 0.0:
                    continue
                gap = now - stats._last_msg_time
                if gap > self._gap_threshold_sec and stats._cached_status != "danger":
                    self._log_manager.add(
                        "danger",
                        f"{stats.name}: no data for {gap:.1f}s",
                        stats.name,
                    )

    def on_message(self, topic_name: str, msg: Any) -> None:
        """Process an incoming message: update statistics and detect gaps.

        Called at very high rates (e.g. 500Hz x 6 topics = 3000 calls/sec), so
        keep the work performed under the lock minimal.

        monotonic: used for stall detection (no message also means no stamp),
        frequency computation, and window bookkeeping.
        header.stamp: used for loss detection, where per-interval thresholding
        needs a jitter-free value.
        """
        if self._paused:
            return
        now = time.monotonic()

        # Extract header.stamp (None when the message type has no header).
        stamp = extract_stamp_sec(msg)

        with self._lock:
            stats = self._topic_stats.get(topic_name)
            if stats is None:
                return

            # Record the first-receive time (monotonic).
            if stats.first_received_at is None:
                stats.first_received_at = now

            # Stall detection (monotonic-based: detects "no messages arriving").
            if stats.message_count > 0 and stats._last_msg_time > 0:
                gap = now - stats._last_msg_time
                if gap > self._gap_threshold_sec:
                    stats.total_gap_sec += gap
                    stats.gaps.append(GapRecord(timestamp=now, duration=gap))
                    if len(stats.gaps) > 20:
                        stats.gaps = stats.gaps[-20:]
                    self._log_manager.add(
                        "danger",
                        f"{topic_name}: detected a gap of {gap:.1f}s",
                        topic_name,
                    )

            # Timestamp handling.
            # _last_msg_time: stall detection (monotonic).
            # on_stamp: Hz counter (monotonic) + loss detection (stamp).
            stats._last_msg_time = now
            stats.on_stamp(now, stamp)
            stats.message_count += 1
            stats.tick_loss_window(now)

            # Live mode.
            is_live = stats._live_mode

            # Live mode: capture sensor position data (O(1) under the lock).
            if is_live and not self._is_image_topic(stats.msg_type):
                self._capture_live_positions(stats, msg)

            # Image topics: always swap in the raw bytes (for MJPEG; O(1) under the lock).
            if self._is_image_topic(stats.msg_type):
                with contextlib.suppress(Exception):
                    stats._live_raw_image = bytes(msg.data) if hasattr(msg, "data") else b""

            # Check the on-demand capture flag (only set by API requests).
            should_capture = stats._capture_next and self._subscriber is not None
            if should_capture:
                stats._capture_next = False

        # Run the expensive conversion outside the lock.
        if should_capture:
            converted = self._subscriber.convert_message(msg)  # type: ignore[union-attr]
            with self._lock:
                stats = self._topic_stats.get(topic_name)
                if stats is not None:
                    stats.latest_message = converted

    def _reserve_subscriptions(self) -> list[TopicStats]:
        """Register stats for desired topics that are discovered but not yet subscribed.

        Caller must hold the lock. Inserting the TopicStats before the DDS
        subscription exists reserves the topic, so a concurrent
        on_discover_tick / update_subscriptions never subscribes twice. The
        returned entries must be handed to _subscribe_reserved() once the
        lock is released.
        """
        if self._subscriber is None:
            return []

        reserved: list[TopicStats] = []
        for name in sorted(self._subscribed_topic_names):
            if name in self._topic_stats or name not in self._discovered_topics:
                continue
            stats = TopicStats(
                name=name,
                msg_type=self._discovered_topics[name],
                is_subscribed=True,
                _gap_threshold_sec=self._gap_threshold_sec,
                stamp_quality=self._stamp_quality,
            )
            # Resolve the expected Hz from the YAML config (fixed baseline).
            if self._resolve_expected_hz is not None:
                expected_hz = self._resolve_expected_hz(name)
                if expected_hz is not None:
                    stats.baseline_hz = expected_hz
                    stats.baseline_fixed = True
                logger.debug("Resolved expected Hz for %s: %s", name, expected_hz)
            self._topic_stats[name] = stats
            reserved.append(stats)
        return reserved

    def _subscribe_reserved(self, reserved: list[TopicStats]) -> None:
        """Create the DDS subscriptions for topics reserved by _reserve_subscriptions().

        Must be called WITHOUT holding the lock: subscribe_topic() blocks on
        DDS discovery, and holding the lock across it would stall every API
        request behind it. Only the bookkeeping of the result runs under the lock.
        """
        for stats in reserved:
            assert self._subscriber is not None  # _reserve_subscriptions() returns [] without a subscriber
            rel_str = self._subscriber.subscribe_topic(stats.name, stats.msg_type, self.on_message)

            with self._lock:
                # The reservation may have been dropped by update_subscriptions()
                # while the DDS call was in flight.
                still_wanted = self._topic_stats.get(stats.name) is stats
                if rel_str is None and still_wanted:
                    self._topic_stats.pop(stats.name)
                elif rel_str is not None and still_wanted:
                    self._subscribed_set.add(stats.name)
                    stats.qos_reliability = rel_str

            if rel_str is None:
                self._log_manager.add("warning", f"Cannot subscribe: unknown type {stats.msg_type}", stats.name)
                continue
            if not still_wanted:
                self._subscriber.unsubscribe_topic(stats.name)
                continue

            hz_info = f", baseline Hz: {stats.baseline_hz:.0f}Hz (fixed)" if stats.baseline_fixed else ""
            self._log_manager.add(
                "info",
                f"Subscribed to {stats.name} ({stats.msg_type}, QoS: {rel_str}{hz_info})",
                stats.name,
            )
            logger.info("Subscribed to %s (%s, QoS: %s)", stats.name, stats.msg_type, rel_str)

    @staticmethod
    def _is_image_topic(msg_type: str) -> bool:
        """Return whether a topic carries image data."""
        return "Image" in msg_type

    @staticmethod
    def _capture_live_positions(stats: TopicStats, msg: Any) -> None:
        """Extract the position array from a sensor message (run under the lock; O(1))."""
        try:
            # JointState: msg.position, msg.name
            if hasattr(msg, "position") and hasattr(msg, "name"):
                stats._live_positions = list(msg.position)
                if not stats._live_joint_names and msg.name:
                    stats._live_joint_names = list(msg.name)
            # Custom types that wrap a JointState: msg.joint_state.position
            elif hasattr(msg, "joint_state") and hasattr(msg.joint_state, "position"):
                stats._live_positions = list(msg.joint_state.position)
                if not stats._live_joint_names and msg.joint_state.name:
                    stats._live_joint_names = list(msg.joint_state.name)
        except Exception as e:
            # Live streaming must not stop even if extracting position/name fails.
            logger.debug("Failed to extract Live position: %s", e)

    @staticmethod
    def _reset_stats_timing(stats: TopicStats) -> None:
        """Reset timing-related metrics."""
        stats.message_count = 0
        stats.first_received_at = None
        stats.total_gap_sec = 0.0
        stats.gaps.clear()
        stats._window_start = 0.0
        stats._window_count = 0
        stats._last_loss_rate = 0.0
        stats._last_drop_count = 0
        stats._last_msg_time = 0.0
        stats._last_stamp = 0.0
        stats._stamp_window_start = 0.0
        stats._stamp_loss_count = 0
        stats._stamp_msg_count = 0
        stats._hz_count = 0
        stats._hz_count_start = 0.0
        stats._learner.reset()
        stats._cached_actual_hz = 0.0
        stats._cached_at = 0.0
        stats._cached_status = "inactive"
        stats._capture_next = False
