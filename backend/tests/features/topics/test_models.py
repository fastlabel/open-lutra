"""Tests for the internal domain models used by topic monitoring.

Covers TopicStats properties (actual_hz, loss_rate, continuity_score,
status), dynamic baseline learning (maybe_learn_baseline), and its
conversion method (to_api).
"""

from unittest.mock import patch

import pytest

from app.features.topics.models import GapRecord, TopicStats

# ---------------------------------------------------------------------------
# actual_hz
# ---------------------------------------------------------------------------


class TestActualHz:
    """Tests for the counter-based actual_hz property."""

    def _stats(self) -> TopicStats:
        return TopicStats(name="/t", msg_type="std_msgs/msg/String")

    def test_no_messages(self) -> None:
        """The counter has never started -> 0 Hz."""
        stats = self._stats()
        stats.refresh_cache(100.0)
        assert stats.actual_hz == 0.0

    def test_computes_rate(self) -> None:
        """20 messages over 2 s -> ~10 Hz."""
        stats = self._stats()
        for i in range(20):
            stats.on_stamp(100.0 + i * 0.1, None)
        stats.refresh_cache(102.0)
        assert stats.actual_hz == pytest.approx(10.0, abs=0.5)

    def test_window_restarts_when_exceeded(self) -> None:
        """The counting window is discarded once it exceeds 3 s."""
        stats = self._stats()
        for i in range(40):
            stats.on_stamp(100.0 + i * 0.1, None)
        stats.refresh_cache(104.0)
        assert stats.actual_hz == pytest.approx(10.0, abs=0.5)
        assert stats._hz_count == 0
        assert stats._hz_count_start == 104.0

    def test_short_window_keeps_previous_value(self) -> None:
        """A freshly restarted window reports the previous value, not 0 Hz."""
        stats = self._stats()
        for i in range(60):
            stats.on_stamp(100.0 + i * 0.05, None)
        stats.refresh_cache(103.5)  # window exceeded -> restarted at 103.5
        measured = stats.actual_hz
        assert measured == pytest.approx(60 / 3.5, abs=0.1)

        stats.refresh_cache(103.6)  # only 0.1 s into the fresh window
        assert stats.actual_hz == measured

    def test_stalled_topic_decays_to_zero(self) -> None:
        """A publisher that stops drives actual_hz to 0 instead of freezing."""
        stats = self._stats()
        for i in range(90):
            stats.on_stamp(100.0 + i / 30.0, None)  # 30 Hz for 3 s
        stats.refresh_cache(103.0)
        assert stats.actual_hz == pytest.approx(30.0, abs=1.0)

        # No further messages arrive; the monotonic window keeps advancing.
        for now in (104.0, 105.0, 106.0):
            stats.refresh_cache(now)
        assert stats.actual_hz == 0.0


# ---------------------------------------------------------------------------
# maybe_learn_baseline
# ---------------------------------------------------------------------------


class TestMaybeLearnBaseline:
    """Tests for snapshot-based dynamic baseline learning."""

    def _stats(self) -> TopicStats:
        return TopicStats(name="/t", msg_type="std_msgs/msg/String")

    def _feed(self, stats: TopicStats, start: float, count: int, interval: float) -> None:
        """Simulate ``count`` message receipts spaced ``interval`` seconds apart."""
        for i in range(count):
            t = start + i * interval
            if stats.first_received_at is None:
                stats.first_received_at = t
            stats._last_msg_time = t
            stats.message_count += 1

    def test_noop_with_existing_baseline(self) -> None:
        """Topics that already have a baseline (fixed or learned) are skipped."""
        stats = self._stats()
        stats.baseline_hz = 30.0
        self._feed(stats, 100.0, 10, 0.1)
        assert stats.maybe_learn_baseline(200.0) is None
        assert stats._learner._time_start == 0.0

    def test_noop_before_first_message(self) -> None:
        stats = self._stats()
        assert stats.maybe_learn_baseline(100.0) is None
        assert stats._learner._time_start == 0.0

    def test_no_snapshot_during_warmup(self) -> None:
        """The measurement does not start within 1s of the first message."""
        stats = self._stats()
        self._feed(stats, 100.0, 5, 0.1)
        assert stats.maybe_learn_baseline(100.9) is None
        assert stats._learner._time_start == 0.0

    def test_snapshot_taken_after_warmup(self) -> None:
        """After the warmup, the current count/time pair is snapshotted (no lock-in yet)."""
        stats = self._stats()
        self._feed(stats, 100.0, 15, 0.1)
        assert stats.maybe_learn_baseline(101.5) is None
        assert stats._learner._time_start == 101.5
        assert stats._learner._count_start == 15

    def test_not_locked_below_min_samples(self) -> None:
        """Enough time but fewer than 50 samples -> keeps measuring."""
        stats = self._stats()
        self._feed(stats, 100.0, 1, 0.1)
        stats.maybe_learn_baseline(101.0)  # snapshot
        self._feed(stats, 101.5, 10, 0.5)  # 10 samples over 4.5s
        assert stats.maybe_learn_baseline(106.5) is None
        assert stats.baseline_hz is None

    def test_not_locked_below_min_duration(self) -> None:
        """Enough samples but a span shorter than 3s -> keeps measuring."""
        stats = self._stats()
        self._feed(stats, 100.0, 1, 0.1)
        stats.maybe_learn_baseline(101.0)  # snapshot
        self._feed(stats, 101.1, 100, 0.01)  # 100 samples over ~1s
        assert stats.maybe_learn_baseline(102.2) is None
        assert stats.baseline_hz is None

    def test_locks_in_and_returns_once(self) -> None:
        """Locks in at 50 samples over >=3s; later calls are no-ops."""
        stats = self._stats()
        self._feed(stats, 100.0, 1, 0.1)
        stats.maybe_learn_baseline(101.0)  # snapshot at count=1
        self._feed(stats, 101.1, 50, 0.1)  # last arrival at 106.0
        learned = stats.maybe_learn_baseline(106.2)
        assert learned == pytest.approx(50 / 5.0, abs=0.01)  # 50 msgs / (106.0 - 101.0)
        assert stats.baseline_hz == learned
        assert stats.maybe_learn_baseline(107.2) is None  # already learned

    def test_burst_before_warmup_excluded(self) -> None:
        """Messages arriving before the snapshot (DDS initial burst) never inflate the result."""
        stats = self._stats()
        self._feed(stats, 100.0, 30, 0.001)  # burst: 30 messages in 30ms
        stats.maybe_learn_baseline(101.0)  # snapshot at count=30
        self._feed(stats, 101.1, 50, 0.1)  # steady 10Hz
        assert stats.maybe_learn_baseline(106.2) == pytest.approx(10.0, abs=0.2)

    def test_stall_before_tick_does_not_dilute(self) -> None:
        """The measurement ends at the last arrival, not at the tick time."""
        stats = self._stats()
        self._feed(stats, 100.0, 1, 0.1)
        stats.maybe_learn_baseline(101.0)  # snapshot
        self._feed(stats, 101.1, 50, 0.1)  # last arrival at 106.0
        # The tick fires long after the topic stalled; elapsed must stop at 106.0.
        assert stats.maybe_learn_baseline(120.0) == pytest.approx(10.0, abs=0.2)

    def test_ultra_slow_topic_learns_nonzero(self) -> None:
        """Intervals longer than the 3s display window still learn the real rate, never 0.0.

        A learned 0.0 would be sticky: baseline_hz stops being None, so learning
        never re-fires, while loss_rate and the warning status both require
        baseline_hz > 0 and would stay disabled until a manual reset.
        """
        stats = self._stats()
        self._feed(stats, 100.0, 1, 1.0)
        stats.maybe_learn_baseline(101.0)  # snapshot
        self._feed(stats, 105.0, 50, 5.0)  # 0.2Hz: last arrival at 350.0
        learned = stats.maybe_learn_baseline(351.0)
        assert learned == pytest.approx(0.2, abs=0.01)
        assert learned > 0


# ---------------------------------------------------------------------------
# loss_rate
# ---------------------------------------------------------------------------


class TestLossRate:
    """Tests for the loss_rate property."""

    def test_no_baseline(self) -> None:
        """When the baseline Hz is unset, returns 0."""
        stats = TopicStats(name="/t", msg_type="std_msgs/msg/String", message_count=100)
        stats.refresh_cache(200.0)
        assert stats.loss_rate == 0.0

    def test_initial_loss_rate_zero(self) -> None:
        """During the first minute (window not yet established) the rate is 0.0."""
        stats = TopicStats(name="/t", msg_type="std_msgs/msg/String", baseline_hz=10.0)
        stats.refresh_cache(100.0)
        assert stats.loss_rate == 0.0

    def test_loss_rate_zero_within_first_second_of_window(self) -> None:
        """A loss window younger than 1s reports 0.0 (not enough data to judge)."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            baseline_hz=10.0,
            message_count=5,
            _last_msg_time=100.4,
            _gap_threshold_sec=3.0,
        )
        for i in range(5):
            stats.tick_loss_window(100.0 + i * 0.1)
        stats.refresh_cache(100.5)
        assert stats.loss_rate == 0.0

    def test_perfect_reception_after_window(self) -> None:
        """All expected messages received over one minute -> loss=0%."""
        stats = TopicStats(name="/t", msg_type="std_msgs/msg/String", baseline_hz=10.0)
        for i in range(600):
            stats.tick_loss_window(100.0 + i * 0.1)
        stats.refresh_cache(160.1)
        assert stats.loss_rate == pytest.approx(0.0, abs=0.02)

    def test_half_lost_after_window(self) -> None:
        """Only half of the expected messages received over one minute -> loss=50%."""
        stats = TopicStats(name="/t", msg_type="std_msgs/msg/String", baseline_hz=10.0)
        for i in range(300):
            stats.tick_loss_window(100.0 + i * 0.2)
        stats.refresh_cache(160.1)
        assert stats.loss_rate == pytest.approx(0.5, abs=0.02)

    @patch("app.features.topics.models.time.monotonic", return_value=110.0)
    def test_danger_returns_zero(self, _mock_time: object) -> None:
        """Returns 0.0 in the danger state."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            baseline_hz=10.0,
            message_count=1,
            _last_msg_time=100.0,
            _gap_threshold_sec=3.0,
            _last_loss_rate=0.3,
        )
        stats.refresh_cache(110.0)
        assert stats.status == "danger"
        assert stats.loss_rate == 0.0


# ---------------------------------------------------------------------------
# continuity_score
# ---------------------------------------------------------------------------


class TestContinuityScore:
    """Tests for the continuity_score property."""

    def test_no_first_received(self) -> None:
        """Returns 1.0 (no issue) when nothing has been received yet."""
        stats = TopicStats(name="/t", msg_type="std_msgs/msg/String")
        assert stats.continuity_score == 1.0

    @patch("app.features.topics.models.time.monotonic", return_value=110.0)
    def test_no_gaps(self, _mock_time: object) -> None:
        """Returns 1.0 when there are no gaps."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            first_received_at=100.0,
            total_gap_sec=0.0,
        )
        assert stats.continuity_score == 1.0

    @patch("app.features.topics.models.time.monotonic", return_value=110.0)
    def test_with_gaps(self, _mock_time: object) -> None:
        """With a 5 s gap inside the most recent 60 s window: 1 - 5/10 = 0.5."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            first_received_at=100.0,
            gaps=[GapRecord(timestamp=105.0, duration=5.0)],
        )
        assert stats.continuity_score == pytest.approx(0.5, abs=0.01)

    @patch("app.features.topics.models.time.monotonic", return_value=100.0)
    def test_elapsed_zero(self, _mock_time: object) -> None:
        """When elapsed time is zero, returns 1.0 (avoids division by zero)."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            first_received_at=100.0,
        )
        assert stats.continuity_score == 1.0


# ---------------------------------------------------------------------------
# last_received_at
# ---------------------------------------------------------------------------


class TestLastReceivedAt:
    """Tests for the last_received_at property."""

    def test_empty(self) -> None:
        stats = TopicStats(name="/t", msg_type="std_msgs/msg/String")
        assert stats.last_received_at is None

    def test_with_last_msg_time(self) -> None:
        stats = TopicStats(name="/t", msg_type="std_msgs/msg/String", _last_msg_time=3.0)
        assert stats.last_received_at == 3.0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatus:
    """Tests for the status property."""

    def test_inactive_no_messages(self) -> None:
        stats = TopicStats(name="/t", msg_type="std_msgs/msg/String")
        stats.refresh_cache(100.0)
        assert stats.status == "inactive"

    def test_ok_recent_message(self) -> None:
        """ok when a message was received recently."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            message_count=1,
            _last_msg_time=100.0,
            _gap_threshold_sec=3.0,
        )
        stats.refresh_cache(100.5)
        assert stats.status == "ok"

    def test_danger_stale(self) -> None:
        """danger when the threshold (3 s) is exceeded."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            message_count=1,
            _last_msg_time=100.0,
            _gap_threshold_sec=3.0,
        )
        stats.refresh_cache(110.0)
        assert stats.status == "danger"

    def test_warning_hz_drop(self) -> None:
        """warning when Hz drops below 50% of baseline."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            message_count=2,
            baseline_hz=10.0,
            _last_msg_time=100.0,
            _gap_threshold_sec=3.0,
        )
        stats.on_stamp(99.0, None)
        stats.on_stamp(100.0, None)
        stats.refresh_cache(100.5)  # 2 messages over 1.5 s -> 1.3 Hz
        assert stats.status == "warning"

    def test_inactive_with_count_but_no_last_msg_time(self) -> None:
        """inactive when message_count > 0 but _last_msg_time is 0."""
        stats = TopicStats(
            name="/t",
            msg_type="std_msgs/msg/String",
            message_count=5,
        )
        stats.refresh_cache(100.0)
        assert stats.status == "inactive"


# ---------------------------------------------------------------------------
# to_api
# ---------------------------------------------------------------------------


class TestToApi:
    """Tests for to_api()."""

    def test_returns_topic_info(self) -> None:
        stats = TopicStats(
            name="/joint_states",
            msg_type="sensor_msgs/msg/JointState",
            message_count=50,
            is_subscribed=True,
            qos_reliability="RELIABLE",
            _last_msg_time=100.49,
            _gap_threshold_sec=3.0,
        )
        for i in range(50):
            stats.on_stamp(100.0 + i * 0.01, None)
        stats.refresh_cache(100.5)
        info = stats.to_api()
        assert info.name == "/joint_states"
        assert info.msg_type == "sensor_msgs/msg/JointState"
        assert info.actual_hz > 0
        assert info.is_subscribed is True
        assert info.qos_reliability == "RELIABLE"
        assert info.message_count == 50


# ---------------------------------------------------------------------------
# stamp-based quality (stamp_quality=True)
# ---------------------------------------------------------------------------


class TestStampBasedQuality:
    """Tests for stamp-interval loss counting and the stamp-based loss rate."""

    def test_on_stamp_counts_losses_from_intervals(self) -> None:
        stats = TopicStats(name="/t", msg_type="x", baseline_hz=10.0, baseline_fixed=True, stamp_quality=True)
        stats.on_stamp(100.0, 1000.0)  # first stamp
        stats.on_stamp(100.1, 1000.5)  # 0.5 s gap at 10 Hz -> ~4 lost
        assert stats._stamp_loss_count == 4
        stats.on_stamp(100.2, 1000.6)  # 0.1 s gap -> jitter, no extra loss
        assert stats._stamp_loss_count == 4
        assert stats._stamp_msg_count == 3

    def test_stamp_based_loss_rate(self) -> None:
        stats = TopicStats(
            name="/t",
            msg_type="x",
            baseline_hz=10.0,
            baseline_fixed=True,
            stamp_quality=True,
            message_count=10,
            _last_msg_time=100.0,
            _gap_threshold_sec=3.0,
        )
        stats._stamp_window_start = 100.0
        stats._stamp_msg_count = 8
        stats._stamp_loss_count = 2
        stats.refresh_cache(101.5)  # stamp_elapsed 1.5 s
        assert stats.loss_rate == pytest.approx(0.2, abs=0.001)  # 2 / (8 + 2)

    def test_stamp_based_loss_rate_resets_window(self) -> None:
        stats = TopicStats(
            name="/t",
            msg_type="x",
            baseline_hz=10.0,
            baseline_fixed=True,
            stamp_quality=True,
            message_count=10,
            _last_msg_time=100.0,
            _gap_threshold_sec=100.0,
        )
        stats._stamp_window_start = 100.0
        stats._stamp_msg_count = 50
        stats._stamp_loss_count = 5
        stats.refresh_cache(106.0)  # stamp_elapsed 6 s >= 5 s window -> reset
        assert stats._stamp_window_start == 106.0
        assert stats._stamp_loss_count == 0
        assert stats._stamp_msg_count == 0
