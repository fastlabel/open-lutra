"""Unit tests for TopicMonitorService.

Mocks the TopicSubscriber Protocol so that the domain logic
can be tested without depending on rclpy.
"""

import time
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from app.features.topics.service import TopicMonitorService
from app.shared.log_manager import LogManager


class _NoHeaderMsg:
    """Mock message for which extract_stamp_sec returns None."""


def _mock_msg() -> _NoHeaderMsg:
    return _NoHeaderMsg()


def _learn_baseline(monitor: TopicMonitorService, topic: str, start: float) -> None:
    """Drive a 10Hz message flow and stats polls under a mocked clock until the baseline locks in."""
    clock = [start]
    with patch("app.features.topics.service.time.monotonic", side_effect=lambda: clock[0]):
        monitor.on_message(topic, _mock_msg())  # first message anchors the warmup
        clock[0] = start + 1.0
        monitor.get_topic_stats()  # warmup elapsed -> measurement snapshot
        for i in range(60):  # >=50 samples spanning >=3s
            clock[0] = start + 1.0 + (i + 1) * 0.1
            monitor.on_message(topic, _mock_msg())
        clock[0] = start + 7.5
        monitor.get_topic_stats()  # lock-in tick


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInit:
    """Initialization tests for TopicMonitorService."""

    def test_initial_state(self, monitor: TopicMonitorService) -> None:
        """Initial state has empty stats."""
        assert monitor.get_topic_stats() == []
        assert monitor.get_discovered_topics() == []

    def test_init_logs_startup(self, log_manager: LogManager) -> None:
        """A log entry is recorded at initialization."""
        TopicMonitorService(subscribed_topics=[], log_manager=log_manager)
        logs, total = log_manager.get_logs()
        assert total >= 1
        assert any("Topic monitoring started" in log.message for log in logs)


# ---------------------------------------------------------------------------
# on_discover_tick
# ---------------------------------------------------------------------------


class TestOnDiscoverTick:
    """Tests for on_discover_tick()."""

    def test_discovers_and_subscribes(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """A discovered topic that is in the subscribe list is subscribed to."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()

        # subscribe was called
        mock_subscriber.subscribe_topic.assert_called_once()
        assert len(monitor.get_topic_stats()) == 1

    def test_ignores_system_topics(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """System topics (/rosout, /parameter_events) are ignored."""
        mock_subscriber.discover_topics.return_value = [
            ("/rosout", ["rcl_interfaces/msg/Log"]),
            ("/parameter_events", ["rcl_interfaces/msg/ParameterEvent"]),
            ("/events/something", ["std_msgs/msg/String"]),
        ]
        monitor.on_discover_tick()
        mock_subscriber.subscribe_topic.assert_not_called()

    def test_discovers_non_subscribed_topics(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """Topics that are not in the subscribe list are added to discovered_topics."""
        mock_subscriber.discover_topics.return_value = [
            ("/camera/image", ["sensor_msgs/msg/Image"]),
        ]
        monitor.on_discover_tick()
        discovered = monitor.get_discovered_topics()
        assert len(discovered) == 1
        assert discovered[0].name == "/camera/image"
        assert discovered[0].is_subscribed is False

    def test_subscribe_failure_logged(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock, log_manager: LogManager
    ) -> None:
        """If subscribe fails, it is logged and not added to stats."""
        mock_subscriber.subscribe_topic.return_value = None  # Failure
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["unknown/msg/Type"]),
        ]
        monitor.on_discover_tick()
        assert len(monitor.get_topic_stats()) == 0
        logs, _ = log_manager.get_logs()
        assert any("Cannot subscribe" in log.message for log in logs)

    def test_no_subscriber_noop(self, log_manager: LogManager) -> None:
        """Does nothing when the subscriber is not set."""
        service = TopicMonitorService(subscribed_topics=[], log_manager=log_manager)
        service.on_discover_tick()  # No exception raised


# ---------------------------------------------------------------------------
# on_message
# ---------------------------------------------------------------------------


class TestOnMessage:
    """Tests for on_message()."""

    def _setup_subscribed(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """Helper that puts the topic into a subscribed state."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()

    def test_message_count_increments(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """Message receipt increments the counter."""
        self._setup_subscribed(monitor, mock_subscriber)
        monitor.on_message("/joint_states", _mock_msg())
        stats = monitor.get_topic_stats()
        assert stats[0].message_count == 1

    def test_unknown_topic_ignored(self, monitor: TopicMonitorService) -> None:
        """Messages on unregistered topics are ignored."""
        monitor.on_message("/unknown_topic", _mock_msg())
        assert monitor.get_topic_stats() == []

    def test_gap_detection(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock, log_manager: LogManager
    ) -> None:
        """A gap exceeding the threshold is detected and logged (gap below the danger threshold)."""
        self._setup_subscribed(monitor, mock_subscriber)

        # Establish the ok state with multiple messages
        for _ in range(5):
            monitor.on_message("/joint_states", _mock_msg())

        stats_dict = monitor._topic_stats
        topic_stats = stats_dict["/joint_states"]
        # Slightly over gap_threshold_sec (3.5 s); raise the threshold so it does not flip to danger
        topic_stats._gap_threshold_sec = 100.0  # Prevents status from going to danger
        monitor._gap_threshold_sec = 3.0  # Service-side gap detection threshold stays at 3 s

        # Shift the last message time back by 3.5 s
        topic_stats._last_msg_time = time.monotonic() - 3.5

        # Next message -> gap detection (not danger, so not reset)
        monitor.on_message("/joint_states", _mock_msg())

        logs, _ = log_manager.get_logs()
        assert any("detected a gap" in log.message for log in logs)

    def test_danger_to_ok_resets_metrics(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """A gap is recorded when recovering from danger to ok."""
        self._setup_subscribed(monitor, mock_subscriber)
        stats = monitor._topic_stats["/joint_states"]

        # Receive messages to bump the count
        for _ in range(10):
            monitor.on_message("/joint_states", _mock_msg())
        assert stats.message_count == 10

        # Create the danger state (set _last_msg_time to an old value)
        stats._last_msg_time = time.monotonic() - 5.0
        stats.refresh_cache(time.monotonic())
        assert stats.status == "danger"

        # Next message recovers to ok -> a gap is recorded
        monitor.on_message("/joint_states", _mock_msg())
        stats.refresh_cache(time.monotonic())
        assert stats.status == "ok"
        assert stats.total_gap_sec > 0.0  # 5-s gap is recorded

    def test_gaps_truncated_to_20(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """Gap records are truncated to the most recent 20."""
        self._setup_subscribed(monitor, mock_subscriber)
        stats = monitor._topic_stats["/joint_states"]

        for _ in range(25):
            # Simulate a large gap between each message
            monitor.on_message("/joint_states", _mock_msg())
            stats._last_msg_time = time.monotonic() - 5.0  # Set to 5 s ago

        # Final gap detected on the last message
        monitor.on_message("/joint_states", _mock_msg())

        assert len(stats.gaps) <= 20

    def test_baseline_hz_learned(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock, log_manager: LogManager
    ) -> None:
        """Baseline Hz locks in after the warmup once >=50 samples span >=3s, and is logged."""
        self._setup_subscribed(monitor, mock_subscriber)
        _learn_baseline(monitor, "/joint_states", start=100.0)

        stats = monitor.get_topic_stats()
        assert stats[0].baseline_hz == pytest.approx(10.0, abs=0.5)
        logs, _ = log_manager.get_logs()
        assert any("Baseline Hz" in log.message for log in logs)

    def test_baseline_not_learned_during_warmup(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """No measurement starts while the warmup second has not elapsed since the first message."""
        self._setup_subscribed(monitor, mock_subscriber)
        clock = [100.0]
        with patch("app.features.topics.service.time.monotonic", side_effect=lambda: clock[0]):
            for i in range(50):
                clock[0] = 100.0 + i * 0.01
                monitor.on_message("/joint_states", _mock_msg())
            clock[0] = 100.6  # < 1s after the first message
            stats = monitor.get_topic_stats()
        assert stats[0].baseline_hz is None

    def test_baseline_unaffected_by_stats_polling_during_learning(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock
    ) -> None:
        """Stats polls (SSE ticks) interleaved with a slow topic's learning must not corrupt the baseline.

        The polls restart the actual_hz tumbling window; the learning measurement
        is snapshot-based on message_count and must stay unaffected.
        """
        self._setup_subscribed(monitor, mock_subscriber)
        clock = [100.0]
        with patch("app.features.topics.service.time.monotonic", side_effect=lambda: clock[0]):
            # 2Hz topic with a stats poll every second.
            for i in range(60):
                clock[0] = 100.0 + i * 0.5
                monitor.on_message("/joint_states", _mock_msg())
                if i % 2 == 0:
                    monitor.get_topic_stats()
            clock[0] = 130.5
            stats = monitor.get_topic_stats()
        assert stats[0].baseline_hz == pytest.approx(2.0, abs=0.1)

    def test_latest_message_updated(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """latest_message is updated on message receipt (1 in every 10)."""
        self._setup_subscribed(monitor, mock_subscriber)
        # Enable _capture_next then send once
        stats = monitor._topic_stats["/joint_states"]
        stats._capture_next = True
        monitor.on_message("/joint_states", _mock_msg())
        msg = monitor.get_latest_message("/joint_states")
        assert msg is not None


# ---------------------------------------------------------------------------
# on_gap_check_tick
# ---------------------------------------------------------------------------


class TestOnGapCheckTick:
    """Tests for on_gap_check_tick()."""

    def test_skips_topic_with_no_messages(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock, log_manager: LogManager
    ) -> None:
        """Topics with message_count=0 are skipped."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        # Run gap_check without any messages -> skipped
        monitor.on_gap_check_tick()
        logs, _ = log_manager.get_logs()
        assert not any("no data" in log.message for log in logs)

    def test_skips_topic_with_no_last_received(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock, log_manager: LogManager
    ) -> None:
        """Skipped when message_count > 0 but _last_msg_time is 0."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        # Manually set message_count; _last_msg_time stays at 0 (defensive coding)
        stats = monitor._topic_stats["/joint_states"]
        stats.message_count = 5

        monitor.on_gap_check_tick()
        logs, _ = log_manager.get_logs()
        assert not any("no data" in log.message for log in logs)

    def test_logs_stale_non_danger_topic(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock, log_manager: LogManager
    ) -> None:
        """Only stale topics whose status is not danger are logged."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        monitor.on_message("/joint_states", _mock_msg())

        stats = monitor._topic_stats["/joint_states"]
        # Create a gap longer than service._gap_threshold_sec (3.0) while keeping
        # stats._gap_threshold_sec large enough that the status judgment does not become danger
        stats._gap_threshold_sec = 100.0
        stats._last_msg_time = time.monotonic() - 4.0
        stats.refresh_cache(time.monotonic())

        monitor.on_gap_check_tick()
        logs, _ = log_manager.get_logs()
        gap_check_logs = [log for log in logs if "no data" in log.message]
        assert len(gap_check_logs) == 1

    def test_dedup_already_danger_topic(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock, log_manager: LogManager
    ) -> None:
        """Topics already in the danger state suppress duplicate logs."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        for _ in range(5):
            monitor.on_message("/joint_states", _mock_msg())

        stats = monitor._topic_stats["/joint_states"]
        stats._last_msg_time = time.monotonic() - 4.0
        stats.refresh_cache(time.monotonic())

        # status=danger, so no log is recorded
        monitor.on_gap_check_tick()
        logs, _ = log_manager.get_logs()
        gap_check_logs = [log for log in logs if "no data" in log.message]
        assert gap_check_logs == []


# ---------------------------------------------------------------------------
# update_subscriptions
# ---------------------------------------------------------------------------


class TestUpdateSubscriptions:
    """Tests for update_subscriptions()."""

    def test_add_new_topic(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """A new topic is added."""
        # Discover first
        mock_subscriber.discover_topics.return_value = [
            ("/camera/image", ["sensor_msgs/msg/Image"]),
        ]
        monitor.on_discover_tick()
        # Update the subscribe list
        result = monitor.update_subscriptions(["/joint_states", "/camera/image"])
        assert "/camera/image" in result

    def test_remove_topic(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """A topic is unsubscribed."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        assert len(monitor.get_topic_stats()) == 1

        # Drop /joint_states
        result = monitor.update_subscriptions([])
        assert "/joint_states" not in result
        assert len(monitor.get_topic_stats()) == 0
        mock_subscriber.unsubscribe_topic.assert_called_with("/joint_states")


# ---------------------------------------------------------------------------
# get_latest_message
# ---------------------------------------------------------------------------


class TestSubscribeWithoutSubscriber:
    """Subscribe behavior tests when no subscriber is set."""

    def test_update_subscriptions_without_subscriber(self, log_manager: LogManager) -> None:
        """update_subscriptions still works (no exceptions) when the subscriber is unset."""
        service = TopicMonitorService(subscribed_topics=[], log_manager=log_manager)
        # Manually register a topic into _discovered_topics (discovery is impossible without a subscriber)
        service._discovered_topics["/camera/image"] = "sensor_msgs/msg/Image"
        result = service.update_subscriptions(["/camera/image"])
        # Without a subscriber, no subscription is created
        assert "/camera/image" not in result
        assert len(service.get_topic_stats()) == 0


class TestGetLatestMessage:
    """Tests for get_latest_message()."""

    def test_returns_none_for_unknown_topic(self, monitor: TopicMonitorService) -> None:
        assert monitor.get_latest_message("/unknown") is None


class TestResetBaseline:
    """Tests for reset_baseline()."""

    def _setup_with_baseline(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """Helper that puts the topic in a state where the baseline Hz has been learned."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        _learn_baseline(monitor, "/joint_states", start=100.0)

    def test_resets_baseline_hz(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """baseline_hz is reset to None."""
        self._setup_with_baseline(monitor, mock_subscriber)
        stats = monitor.get_topic_stats()
        assert stats[0].baseline_hz is not None

        monitor.reset_baseline()
        stats = monitor.get_topic_stats()
        assert stats[0].baseline_hz is None

    def test_resets_counters(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """message_count, loss_rate, etc. are reset."""
        self._setup_with_baseline(monitor, mock_subscriber)
        monitor.reset_baseline()
        stats = monitor.get_topic_stats()
        assert stats[0].message_count == 0
        assert stats[0].loss_rate == 0.0

    def test_relearns_after_reset(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """After reset, a fresh warmup + measurement cycle re-learns the correct baseline Hz.

        The value assertion matters: a learner still holding its pre-reset
        snapshot would relearn against the restarted message_count and produce
        a wildly low Hz instead of failing outright.
        """
        self._setup_with_baseline(monitor, mock_subscriber)
        monitor.reset_baseline()
        _learn_baseline(monitor, "/joint_states", start=200.0)
        stats = monitor.get_topic_stats()
        assert stats[0].baseline_hz == pytest.approx(10.0, abs=0.5)

    def test_logs_reset(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock, log_manager: LogManager
    ) -> None:
        """A log entry is written when reset."""
        self._setup_with_baseline(monitor, mock_subscriber)
        monitor.reset_baseline()
        logs, _ = log_manager.get_logs()
        assert any("reset" in log.message.lower() for log in logs)


class TestPauseResume:
    """Tests for pause() / resume()."""

    def test_pause_skips_on_message(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """on_message is skipped while paused."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        monitor.on_message("/joint_states", _mock_msg())
        assert monitor.get_topic_stats()[0].message_count == 1

        monitor.pause()
        monitor.on_message("/joint_states", _mock_msg())
        assert monitor.get_topic_stats()[0].message_count == 1  # No increment

    def test_resume_restores_on_message(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        """After resume, on_message is processed normally again."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        monitor.pause()
        monitor.on_message("/joint_states", _mock_msg())

        monitor.resume()
        monitor.on_message("/joint_states", _mock_msg())
        assert monitor.get_topic_stats()[0].message_count == 1

    def test_resume_clears_metrics_but_keeps_baseline(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock
    ) -> None:
        """On resume, timing metrics are reset but baseline_hz is preserved."""
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        _learn_baseline(monitor, "/joint_states", start=100.0)
        baseline = monitor.get_topic_stats()[0].baseline_hz
        assert baseline is not None

        monitor.pause()
        monitor.resume()

        stats = monitor.get_topic_stats()[0]
        assert stats.baseline_hz == baseline  # Preserved
        assert stats.message_count == 0  # reset
        assert stats.loss_rate == 0.0  # reset

    def test_pause_logs(self, monitor: TopicMonitorService, log_manager: LogManager) -> None:
        """A log entry is written on pause."""
        monitor.pause()
        logs, _ = log_manager.get_logs()
        assert any("paused" in log.message.lower() for log in logs)

    def test_resume_logs(self, monitor: TopicMonitorService, log_manager: LogManager) -> None:
        """A log entry is written on resume."""
        monitor.pause()
        monitor.resume()
        logs, _ = log_manager.get_logs()
        assert any("resumed" in log.message.lower() for log in logs)


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------


class TestLiveMode:
    """Live-mode accessors (used by image/sensor SSE streaming)."""

    def _subscribe_joint(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        mock_subscriber.discover_topics.return_value = [("/joint_states", ["sensor_msgs/msg/JointState"])]
        monitor.on_discover_tick()

    def test_is_live_defaults_false(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        assert monitor.is_live("/joint_states") is False
        assert monitor.is_live("/unknown") is False

    def test_start_live_sets_live(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        assert monitor.start_live("/joint_states") is True
        assert monitor.is_live("/joint_states") is True

    def test_start_live_unknown_returns_false(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        assert monitor.start_live("/missing") is False

    def test_start_live_stops_other_sessions(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock
    ) -> None:
        mock_subscriber.discover_topics.return_value = [
            ("/joint_states", ["sensor_msgs/msg/JointState"]),
            ("/arm_states", ["sensor_msgs/msg/JointState"]),
        ]
        monitor.on_discover_tick()
        monitor.update_subscriptions(["/joint_states", "/arm_states"])
        monitor.start_live("/joint_states")
        monitor.start_live("/arm_states")
        assert monitor.is_live("/joint_states") is False
        assert monitor.is_live("/arm_states") is True

    def test_stop_live(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        monitor.start_live("/joint_states")
        monitor.stop_live("/joint_states")
        assert monitor.is_live("/joint_states") is False

    def test_stop_live_unknown_is_noop(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        monitor.stop_live("/missing")  # no exception

    def test_get_live_raw_image(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        assert monitor.get_live_raw_image("/missing") == b""
        monitor._topic_stats["/joint_states"]._live_raw_image = b"frame"
        assert monitor.get_live_raw_image("/joint_states") == b"frame"

    def test_get_live_positions_none_when_not_live(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock
    ) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        assert monitor.get_live_positions("/missing") is None
        assert monitor.get_live_positions("/joint_states") is None  # not in live mode

    def test_get_live_positions_none_when_empty(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock
    ) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        monitor.start_live("/joint_states")
        assert monitor.get_live_positions("/joint_states") is None  # nothing captured yet

    def test_get_live_positions_returns_data(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock
    ) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        monitor.start_live("/joint_states")
        stats = monitor._topic_stats["/joint_states"]
        stats._live_positions = [1.0, 2.0]
        stats._live_joint_names = ["a", "b"]
        assert monitor.get_live_positions("/joint_states") == {"positions": [1.0, 2.0], "names": ["a", "b"]}


class TestOnMessageLiveCapture:
    """on_message branches for live capture and image raw-byte swapping."""

    def _subscribe_joint(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        mock_subscriber.discover_topics.return_value = [("/joint_states", ["sensor_msgs/msg/JointState"])]
        monitor.on_discover_tick()

    def test_live_joint_capture(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        monitor.start_live("/joint_states")
        monitor.on_message("/joint_states", SimpleNamespace(position=[1.0, 2.0], name=["a", "b"]))
        assert monitor.get_live_positions("/joint_states") == {"positions": [1.0, 2.0], "names": ["a", "b"]}

    def test_live_wrapped_joint_capture(self, monitor: TopicMonitorService, mock_subscriber: MagicMock) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        monitor.start_live("/joint_states")
        msg = SimpleNamespace(joint_state=SimpleNamespace(position=[3.0], name=["j1"]))
        monitor.on_message("/joint_states", msg)
        assert monitor.get_live_positions("/joint_states") == {"positions": [3.0], "names": ["j1"]}

    def test_live_capture_handles_extraction_error(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock
    ) -> None:
        self._subscribe_joint(monitor, mock_subscriber)
        monitor.start_live("/joint_states")

        class _Bad:
            name: ClassVar[list[str]] = ["x"]

            @property
            def position(self) -> list[float]:
                raise RuntimeError("boom")

        monitor.on_message("/joint_states", _Bad())  # exception is swallowed
        assert monitor.get_live_positions("/joint_states") is None

    def test_image_topic_captures_raw_bytes(
        self, monitor: TopicMonitorService, mock_subscriber: MagicMock
    ) -> None:
        mock_subscriber.discover_topics.return_value = [("/cam/image", ["sensor_msgs/msg/Image"])]
        monitor.on_discover_tick()
        monitor.update_subscriptions(["/cam/image"])
        monitor.on_message("/cam/image", SimpleNamespace(data=b"\xff\xd8jpeg"))
        assert monitor.get_live_raw_image("/cam/image") == b"\xff\xd8jpeg"


class TestSubscribeExpectedHz:
    """_subscribe_to_topic resolves a fixed baseline from the Hz resolver."""

    def test_fixed_baseline_from_resolver(self, log_manager: LogManager, mock_subscriber: MagicMock) -> None:
        service = TopicMonitorService(
            subscribed_topics=["/joint_states"],
            log_manager=log_manager,
            resolve_expected_hz=lambda _name: 100.0,
        )
        service.set_subscriber(mock_subscriber)
        mock_subscriber.discover_topics.return_value = [("/joint_states", ["sensor_msgs/msg/JointState"])]
        service.on_discover_tick()
        stats = service.get_topic_stats()[0]
        assert stats.baseline_hz == 100.0
        assert stats.baseline_fixed is True

    def test_resolver_returns_none(self, log_manager: LogManager, mock_subscriber: MagicMock) -> None:
        service = TopicMonitorService(
            subscribed_topics=["/joint_states"],
            log_manager=log_manager,
            resolve_expected_hz=lambda _name: None,
        )
        service.set_subscriber(mock_subscriber)
        mock_subscriber.discover_topics.return_value = [("/joint_states", ["sensor_msgs/msg/JointState"])]
        service.on_discover_tick()
        stats = service.get_topic_stats()[0]
        assert stats.baseline_fixed is False
