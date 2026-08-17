"""Thread management for the rclpy TopicMonitor node.

Manages the lifecycle of the background daemon thread that bridges rclpy's
blocking executor and FastAPI's asyncio loop. Acts as the composition root
that wires together the infrastructure layer (TopicMonitorNode) and the
domain service (TopicMonitorService).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import rclpy
from rclpy.executors import SingleThreadedExecutor

from app.features.topics.service import TopicMonitorService
from app.infra.ros2.topic_node import TopicMonitorNode

if TYPE_CHECKING:
    from app.settings import Settings
    from app.shared.log_manager import LogManager

logger = logging.getLogger(__name__)


class TopicMonitorThread:
    """Manages the rclpy TopicMonitor on a background thread."""

    def __init__(self, settings: Settings, log_manager: LogManager) -> None:
        self._settings = settings
        self._log_manager = log_manager
        self._service: TopicMonitorService | None = None
        self._node: TopicMonitorNode | None = None
        self._thread: threading.Thread | None = None
        self._executor: SingleThreadedExecutor | None = None
        self._should_stop = threading.Event()

    def start(self) -> TopicMonitorService:
        """Initialize rclpy and start the monitor thread.

        Returns:
            The TopicMonitorService instance used by API endpoints.
        """
        try:
            rclpy.init()
        except RuntimeError:
            logger.debug("rclpy is already initialized")

        # Create the domain service
        self._service = TopicMonitorService(
            subscribed_topics=self._settings.default_topics,
            log_manager=self._log_manager,
            gap_threshold_sec=self._settings.gap_threshold_sec,
            resolve_expected_hz=self._settings.recording.resolve_expected_hz,
            stamp_quality=self._settings.stamp_quality,
        )

        # Create the infrastructure node and connect it to the service
        self._node = TopicMonitorNode(qos_depth=self._settings.monitor_qos_depth)
        self._service.set_subscriber(self._node)

        # Create timers on the node (callbacks are service methods)
        self._node.create_timer(5.0, self._service.on_discover_tick)
        self._node.create_timer(1.0, self._service.on_gap_check_tick)

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)

        self._thread = threading.Thread(
            target=self._spin_loop,
            daemon=True,
            name="topic-monitor",
        )
        self._thread.start()
        logger.info("TopicMonitor thread started")

        return self._service

    def stop(self) -> None:
        """Stop the monitor thread and shut down rclpy."""
        self._should_stop.set()

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("TopicMonitor thread did not stop in time")

        if self._node is not None:
            self._node.destroy_node()

        if self._executor is not None:
            self._executor.shutdown()

        try:
            rclpy.shutdown()
        except RuntimeError:
            logger.debug("rclpy is already shut down")

        logger.info("TopicMonitor thread stopped")

    @property
    def service(self) -> TopicMonitorService | None:
        """Return the TopicMonitorService instance."""
        return self._service

    def _spin_loop(self) -> None:
        """Spin the executor until a stop is requested."""
        # _spin_loop only starts after start() creates the executor, so it is not None.
        assert self._executor is not None
        while not self._should_stop.is_set():
            self._executor.spin_once(timeout_sec=0.01)
