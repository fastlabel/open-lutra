"""Tests for file-quality analysis domain models."""

from app.features.analysis.models import MessageSizeStats, QualityReport, TopicQuality


class TestEstimateExpectedFrequency:
    """Tests for TopicQuality._estimate_expected_frequency()."""

    def test_exact_match(self) -> None:
        """Matches a standard frequency exactly."""
        assert TopicQuality._estimate_expected_frequency(100.0) == 100.0
        assert TopicQuality._estimate_expected_frequency(30.0) == 30.0

    def test_close_to_standard(self) -> None:
        """Values near a standard frequency are rounded to the nearest standard value."""
        assert TopicQuality._estimate_expected_frequency(99.3) == 100.0
        assert TopicQuality._estimate_expected_frequency(29.5) == 30.0
        assert TopicQuality._estimate_expected_frequency(52.0) == 50.0

    def test_zero(self) -> None:
        assert TopicQuality._estimate_expected_frequency(0.0) == 0.0

    def test_negative(self) -> None:
        assert TopicQuality._estimate_expected_frequency(-10.0) == 0.0

    def test_high_frequency(self) -> None:
        """A value close to 200 Hz."""
        assert TopicQuality._estimate_expected_frequency(198.0) == 200.0

    def test_between_standards(self) -> None:
        """A value roughly midway between two standard values."""
        assert TopicQuality._estimate_expected_frequency(35.0) == 30.0
        assert TopicQuality._estimate_expected_frequency(45.0) == 50.0


class TestCalcSizeStats:
    """Tests for MessageSizeStats.from_sizes()."""

    def test_empty_list(self) -> None:
        """Empty list returns the default values."""
        stats = MessageSizeStats.from_sizes([])
        assert stats.min_bytes == 0
        assert stats.max_bytes == 0
        assert stats.avg_bytes == 0
        assert stats.std_bytes == 0.0
        assert stats.zero_size_count == 0

    def test_single_element(self) -> None:
        """For a single element, std_bytes is 0."""
        stats = MessageSizeStats.from_sizes([100])
        assert stats.min_bytes == 100
        assert stats.max_bytes == 100
        assert stats.avg_bytes == 100
        assert stats.std_bytes == 0.0

    def test_uniform_sizes(self) -> None:
        """When all sizes are the same, std_bytes is 0."""
        stats = MessageSizeStats.from_sizes([150, 150, 150, 150])
        assert stats.min_bytes == 150
        assert stats.max_bytes == 150
        assert stats.avg_bytes == 150
        assert stats.std_bytes == 0.0

    def test_varied_sizes(self) -> None:
        """Sizes with variation."""
        stats = MessageSizeStats.from_sizes([100, 200, 300])
        assert stats.min_bytes == 100
        assert stats.max_bytes == 300
        assert stats.avg_bytes == 200
        assert stats.std_bytes > 0.0

    def test_zero_size_count(self) -> None:
        """Messages with size 0 are counted."""
        stats = MessageSizeStats.from_sizes([0, 100, 0, 200])
        assert stats.zero_size_count == 2


class TestDetermineStatus:
    """Tests for TopicQuality._determine_status().

    danger when there is major_loss (3+ frames lost); warning when there is minor_loss (1-2 frames);
    otherwise ok. Returns ok when msg_count=0.
    """

    def test_ok_no_loss(self) -> None:
        assert TopicQuality._determine_status(major_loss=0, minor_loss=0, msg_count=100) == "ok"

    def test_warning_minor_loss(self) -> None:
        assert TopicQuality._determine_status(major_loss=0, minor_loss=1, msg_count=100) == "warning"

    def test_danger_major_loss(self) -> None:
        assert TopicQuality._determine_status(major_loss=1, minor_loss=0, msg_count=100) == "danger"

    def test_danger_takes_precedence(self) -> None:
        """When both major and minor losses are present, the result is danger."""
        assert TopicQuality._determine_status(major_loss=1, minor_loss=5, msg_count=100) == "danger"

    def test_empty_msg_count_returns_ok(self) -> None:
        """Returns ok when there are no messages (not analyzed)."""
        assert TopicQuality._determine_status(major_loss=0, minor_loss=0, msg_count=0) == "ok"


class TestFromMcapData:
    """Tests for QualityReport.from_mcap_data()."""

    def test_single_topic(self) -> None:
        """Builds a report for a single topic."""
        timestamps = {"/topic_a": [1.0, 1.1, 1.2, 1.3, 1.4]}
        sizes = {"/topic_a": [100, 100, 100, 100, 100]}
        types = {"/topic_a": "sensor_msgs/msg/JointState"}

        report = QualityReport.from_mcap_data(
            topic_timestamps=timestamps,
            topic_sizes=sizes,
            topic_types=types,
            file_size=5000,
        )
        assert report.total_topics == 1
        assert report.total_messages == 5
        assert report.file_size_bytes == 5000
        assert len(report.topics) == 1
        assert report.topics[0].name == "/topic_a"

    def test_empty_data(self) -> None:
        """When there is no data."""
        report = QualityReport.from_mcap_data(
            topic_timestamps={},
            topic_sizes={},
            topic_types={},
            file_size=0,
        )
        assert report.total_topics == 0
        assert report.total_messages == 0

    def test_single_message_topic(self) -> None:
        """A topic with a single message skips frequency analysis."""
        report = QualityReport.from_mcap_data(
            topic_timestamps={"/t": [1.0]},
            topic_sizes={"/t": [100]},
            topic_types={"/t": "std_msgs/msg/String"},
            file_size=100,
        )
        tq = report.topics[0]
        assert tq.message_count == 1
        assert tq.actual_frequency_hz == 0.0
        assert tq.loss_rate == 0.0

    def test_topic_with_gaps(self) -> None:
        """A topic containing gaps yields gap_count > 0."""
        # 0.1s intervals followed by a 1.0s gap (more than 3x the expected interval)
        ts = [0.0, 0.1, 0.2, 0.3, 1.5, 1.6, 1.7]
        report = QualityReport.from_mcap_data(
            topic_timestamps={"/t": ts},
            topic_sizes={"/t": [100] * len(ts)},
            topic_types={"/t": "std_msgs/msg/String"},
            file_size=700,
        )
        tq = report.topics[0]
        assert tq.gap_count >= 1
        assert tq.data_continuity_score < 1.0

    def test_zero_hz_loss_rate(self) -> None:
        """When expected_hz=0, loss_rate becomes 0.0."""
        # Identical timestamps -> median_interval=0 -> actual_hz=0 -> expected_hz=0
        report = QualityReport.from_mcap_data(
            topic_timestamps={"/t": [1.0, 1.0, 1.0]},
            topic_sizes={"/t": [50, 50, 50]},
            topic_types={"/t": "std_msgs/msg/String"},
            file_size=150,
        )
        tq = report.topics[0]
        assert tq.loss_rate == 0.0


# ---------------------------------------------------------------------------
# LossEvent (IQR-based loss detection)
# ---------------------------------------------------------------------------


class TestLossEvents:
    """Tests for TopicQuality._detect_loss_events()."""

    def test_no_loss_in_regular_intervals(self) -> None:
        """For evenly spaced timestamps, loss_events is empty."""
        ts = [i * 0.01 for i in range(200)]  # 100 Hz, perfect
        tq = TopicQuality.from_timestamps(
            name="/t",
            msg_type="sensor_msgs/msg/JointState",
            timestamps=ts,
            sizes=[100] * len(ts),
            recording_start=0.0,
            duration_sec=2.0,
            timestamp_source="header_stamp",
        )
        assert tq.loss_events == []
        assert tq.loss_count == 0

    def test_detects_single_frame_loss(self) -> None:
        """Detects a single-frame loss (a 20 ms gap at 100 Hz)."""
        # 100 Hz: 10 ms interval; one frame missing after index 25 (next sample is 20 ms later)
        ts = [i * 0.01 for i in range(25)]
        # ts[24]=0.24 -> next is 0.26 (20 ms later, one frame lost)
        ts += [0.26 + i * 0.01 for i in range(25)]
        tq = TopicQuality.from_timestamps(
            name="/t",
            msg_type="sensor_msgs/msg/JointState",
            timestamps=ts,
            sizes=[100] * len(ts),
            recording_start=0.0,
            duration_sec=0.5,
            timestamp_source="header_stamp",
        )
        assert len(tq.loss_events) >= 1
        assert tq.loss_events[0].lost_count == 1
        assert tq.loss_events[0].severity == "minor"

    def test_detects_major_loss(self) -> None:
        """A 5-frame loss yields severity=major."""
        # 100 Hz: 10 ms interval, with a gap after 50 ms
        ts = [i * 0.01 for i in range(50)] + [0.5 + 0.06 + i * 0.01 for i in range(50)]
        tq = TopicQuality.from_timestamps(
            name="/t",
            msg_type="sensor_msgs/msg/JointState",
            timestamps=ts,
            sizes=[100] * len(ts),
            recording_start=0.0,
            duration_sec=1.1,
            timestamp_source="header_stamp",
        )
        major_events = [e for e in tq.loss_events if e.severity == "major"]
        assert len(major_events) >= 1
        assert major_events[0].lost_count >= 3

    def test_timestamp_source_recorded(self) -> None:
        """timestamp_source is recorded in the report."""
        ts = [i * 0.01 for i in range(20)]
        tq = TopicQuality.from_timestamps(
            name="/t",
            msg_type="sensor_msgs/msg/JointState",
            timestamps=ts,
            sizes=[100] * len(ts),
            recording_start=0.0,
            duration_sec=0.2,
            timestamp_source="header_stamp",
        )
        assert tq.timestamp_source == "header_stamp"

    def test_too_few_intervals(self) -> None:
        """loss_events is empty when there are fewer than 4 intervals (IQR cannot be computed)."""
        ts = [0.0, 0.01, 0.02]
        tq = TopicQuality.from_timestamps(
            name="/t",
            msg_type="sensor_msgs/msg/JointState",
            timestamps=ts,
            sizes=[100] * len(ts),
            recording_start=0.0,
            duration_sec=0.02,
            timestamp_source="header_stamp",
        )
        assert tq.loss_events == []

    def test_loss_events_sorted_by_timestamp_with_edge_loss(self) -> None:
        """When edge losses (start_delay/end_early) coexist with intermediate gaps, events are ordered by timestamp ascending.

        Regression: before the fix, edge_events were prepended, so end_early appeared before intermediate gaps
        (i.e., at the head of the array). This caused the order to drift away from the UI timeline.
        """
        # 30 Hz (33 ms interval), 10 s recording
        # 1 s start delay (start_delay) + 1 intermediate gap (~7 s mark) + ~1.5 s early end (end_early)
        # -> loss_events should be ordered by timestamp_sec: 0 -> 7 -> 8
        interval = 1 / 30.0
        # Starts at 1.0 s (start_delay = 1.0)
        ts = [1.0 + i * interval for i in range(180)]  # 1.0 to ~7.0 s
        # Insert a 0.2 s gap after ~7.0 s (6 frames lost -> major)
        ts += [7.2 + i * interval for i in range(30)]  # 7.2 to ~8.2 s
        # Then nothing until the 10 s recording end -> end_early ~1.8 s

        tq = TopicQuality.from_timestamps(
            name="/cam",
            msg_type="sensor_msgs/msg/CompressedImage",
            timestamps=ts,
            sizes=[100] * len(ts),
            recording_start=0.0,
            duration_sec=10.0,
            timestamp_source="header_stamp",
        )

        # Should have at least 3 events (start_delay / intermediate gap / end_early)
        assert len(tq.loss_events) >= 3

        # Ensure timestamp_sec values are in ascending order (monotonically increasing)
        timestamps_in_order = [le.timestamp_sec for le in tq.loss_events]
        assert timestamps_in_order == sorted(timestamps_in_order)

        # Head is start_delay (timestamp_sec = 0)
        assert tq.loss_events[0].timestamp_sec == 0.0

        # Tail is end_early (max timestamp_sec ~ 8.2, just before the 10 s recording end)
        assert tq.loss_events[-1].timestamp_sec > 7.0
        assert tq.loss_events[-1].timestamp_sec < 10.0
