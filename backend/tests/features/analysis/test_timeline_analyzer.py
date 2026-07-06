"""Tests for the timeline generation logic.

Functions that perform MCAP I/O (`build_and_save_timeline` / `read_messages_in_range` /
`_resolve_timeline_meta`) are out of scope (`pragma: no cover`).
This covers the pure computation (`_build_timeline` / `_estimate_hz` / `_calc_bin_width` /
`_detect_*` / `load_timeline`) and TimelineAnalyzer state transitions.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.analysis.timeline_analyzer import (
    TimelineAnalyzer,
    _build_timeline,
    _calc_bin_width,
    _detect_edge_loss_for_timeline,
    _detect_loss_events_for_timeline,
    _estimate_hz,
    load_timeline,
)

# ---------------------------------------------------------------------------
# _estimate_hz
# ---------------------------------------------------------------------------


class TestEstimateHz:
    """Tests for _estimate_hz()."""

    def test_too_few_timestamps(self) -> None:
        """Fewer than 2 entries yields 0 Hz."""
        assert _estimate_hz([]) == 0.0
        assert _estimate_hz([1.0]) == 0.0

    def test_30hz(self) -> None:
        """Timestamps spaced at 30 Hz."""
        timestamps = [i / 30.0 for i in range(60)]
        assert _estimate_hz(timestamps) == 30.0

    def test_100hz(self) -> None:
        """Timestamps spaced at 100 Hz."""
        timestamps = [i * 0.01 for i in range(100)]
        assert _estimate_hz(timestamps) == 100.0

    def test_close_to_standard(self) -> None:
        """Values near a standard frequency round to the nearest standard value."""
        # About 29 Hz -> rounded to 30 Hz
        timestamps = [i * (1 / 29.0) for i in range(50)]
        assert _estimate_hz(timestamps) == 30.0

    def test_zero_interval(self) -> None:
        """When all timestamps are identical, returns 0 Hz."""
        assert _estimate_hz([1.0, 1.0, 1.0, 1.0]) == 0.0

    def test_unsorted_input(self) -> None:
        """Computes correctly even when input is unsorted."""
        timestamps = [0.3, 0.0, 0.2, 0.1]
        assert _estimate_hz(timestamps) == 10.0


# ---------------------------------------------------------------------------
# _calc_bin_width
# ---------------------------------------------------------------------------


class TestCalcBinWidth:
    """Tests for _calc_bin_width()."""

    def test_zero_duration(self) -> None:
        """duration=0 returns a 1-second bin width."""
        assert _calc_bin_width(0) == 1.0

    def test_negative_duration(self) -> None:
        """Negative duration returns a 1-second bin width."""
        assert _calc_bin_width(-5) == 1.0

    def test_short_recording(self) -> None:
        """A 30-second recording uses a 0.05-second bin width (600 bins)."""
        assert _calc_bin_width(30.0) == 0.05

    def test_medium_recording(self) -> None:
        """A 5-minute recording picks a width that fits in the 600-1800 bin range."""
        # 300 s -> 0.2 s -> 1500 bins (within range)
        result = _calc_bin_width(300.0)
        bins = 300.0 / result
        assert 600 <= bins <= 1800

    def test_long_recording(self) -> None:
        """A 1-hour recording picks a sufficiently large bin width."""
        result = _calc_bin_width(3600.0)
        assert result > 0
        # Fits within 1800 bins
        assert 3600.0 / result <= 1800


# ---------------------------------------------------------------------------
# _detect_edge_loss_for_timeline
# ---------------------------------------------------------------------------


class TestDetectEdgeLossForTimeline:
    """Tests for _detect_edge_loss_for_timeline()."""

    def test_zero_interval_returns_empty(self) -> None:
        """expected_interval=0 returns nothing."""
        assert (
            _detect_edge_loss_for_timeline(
                first_ts_rel=1.0,
                last_ts_rel=10.0,
                duration_sec=15.0,
                expected_interval=0.0,
            )
            == []
        )

    def test_no_edge_loss(self) -> None:
        """When both head and tail are within the threshold, nothing is detected."""
        events = _detect_edge_loss_for_timeline(
            first_ts_rel=0.01,
            last_ts_rel=9.99,
            duration_sec=10.0,
            expected_interval=0.033,  # 30 Hz
        )
        assert events == []

    def test_start_delay_detected(self) -> None:
        """Detects a leading gap."""
        # 30 Hz, 1 s start delay = ~30 frames lost -> major
        events = _detect_edge_loss_for_timeline(
            first_ts_rel=1.0,
            last_ts_rel=10.0,
            duration_sec=10.0,
            expected_interval=0.033,
        )
        assert len(events) == 1
        assert events[0][0] == 0.0  # start time
        assert events[0][1] == 1.0  # duration
        assert events[0][2] == "major"

    def test_end_early_detected(self) -> None:
        """Detects an early ending."""
        events = _detect_edge_loss_for_timeline(
            first_ts_rel=0.0,
            last_ts_rel=8.0,
            duration_sec=10.0,
            expected_interval=0.033,
        )
        assert len(events) == 1
        assert events[0][0] == 8.0
        assert events[0][1] == 2.0  # duration = 10 - 8
        assert events[0][2] == "major"

    def test_minor_edge_loss(self) -> None:
        """A 1-2 frame loss is minor."""
        # 30 Hz, 0.07 s delay (~2 frames)
        events = _detect_edge_loss_for_timeline(
            first_ts_rel=0.07,
            last_ts_rel=9.99,
            duration_sec=10.0,
            expected_interval=0.033,
        )
        assert len(events) == 1
        assert events[0][2] == "minor"

    def test_both_edges(self) -> None:
        """Detects both the head and tail."""
        events = _detect_edge_loss_for_timeline(
            first_ts_rel=1.0,
            last_ts_rel=8.0,
            duration_sec=10.0,
            expected_interval=0.033,
        )
        assert len(events) == 2


# ---------------------------------------------------------------------------
# _detect_loss_events_for_timeline
# ---------------------------------------------------------------------------


class TestDetectLossEventsForTimeline:
    """Tests for _detect_loss_events_for_timeline()."""

    def test_too_few_timestamps(self) -> None:
        """Fewer than 4 entries detects nothing."""
        assert _detect_loss_events_for_timeline([1.0, 2.0, 3.0], 0.033, 0.0) == []

    def test_zero_interval(self) -> None:
        """expected_interval=0 detects nothing."""
        assert _detect_loss_events_for_timeline([0.0, 0.1, 0.2, 0.3, 0.4], 0.0, 0.0) == []

    def test_no_loss(self) -> None:
        """No detections for regular intervals."""
        timestamps = [i * 0.033 for i in range(30)]
        events = _detect_loss_events_for_timeline(timestamps, 0.033, 0.0)
        assert events == []

    def test_major_loss(self) -> None:
        """A loss of 3 or more frames is major."""
        # Lined up at 0.033 s intervals, with a 0.2 s gap (~6 frames lost) inserted between indices 5 and 6
        timestamps = [i * 0.033 for i in range(20)]
        timestamps[6:] = [t + 0.2 for t in timestamps[6:]]
        events = _detect_loss_events_for_timeline(timestamps, 0.033, 0.0)
        assert len(events) >= 1
        assert any(e[2] == "major" for e in events)

    def test_minor_loss(self) -> None:
        """A 1-2 frame loss is minor."""
        # Lined up at 0.033 s intervals, with 0.05 s added between indices 6 and 7 (~2 frames lost)
        timestamps = [i * 0.033 for i in range(30)]
        timestamps[7:] = [t + 0.05 for t in timestamps[7:]]
        events = _detect_loss_events_for_timeline(timestamps, 0.033, 0.0)
        assert len(events) >= 1
        assert all(e[2] == "minor" for e in events)

    def test_relative_timestamp(self) -> None:
        """Returns seconds relative to recording_start."""
        timestamps = [100.0 + i * 0.033 for i in range(20)]
        timestamps[6:] = [t + 0.2 for t in timestamps[6:]]
        events = _detect_loss_events_for_timeline(timestamps, 0.033, 100.0)
        # Coordinates are relative
        assert all(e[0] < 5.0 for e in events)


# ---------------------------------------------------------------------------
# _build_timeline
# ---------------------------------------------------------------------------


class TestBuildTimeline:
    """Tests for _build_timeline()."""

    def test_empty_input(self) -> None:
        """Empty input returns data with duration=0."""
        data = _build_timeline({}, {})
        assert data.duration_sec == 0
        assert data.bin_width_sec == 1.0
        assert data.topics == []
        assert data.recording_start_ns == 0
        assert data.log_time_offset_ns == 0

    def test_single_topic(self) -> None:
        """Bins are generated correctly for a single topic."""
        timestamps = [i * 0.033 for i in range(30)]
        data = _build_timeline(
            {"/cam": timestamps},
            {"/cam": "sensor_msgs/CompressedImage"},
        )
        assert len(data.topics) == 1
        topic = data.topics[0]
        assert topic.name == "/cam"
        assert topic.msg_type == "sensor_msgs/CompressedImage"
        assert topic.expected_hz == 30.0
        assert len(topic.bins) > 0

    def test_config_expected_hz_overrides_estimate(self) -> None:
        """A configured Hz overrides the estimated expected_hz (matches the quality report)."""
        timestamps = [i * 0.033 for i in range(30)]  # ~30 Hz measured
        data = _build_timeline(
            {"/cam": timestamps},
            {"/cam": "sensor_msgs/CompressedImage"},
            resolve_expected_hz=lambda name: 100.0,
        )
        assert data.topics[0].expected_hz == 100.0

    def test_config_expected_hz_none_falls_back_to_estimate(self) -> None:
        """A resolver returning None leaves the estimated expected_hz in place."""
        timestamps = [i * 0.033 for i in range(30)]  # ~30 Hz measured
        data = _build_timeline(
            {"/cam": timestamps},
            {"/cam": "sensor_msgs/CompressedImage"},
            resolve_expected_hz=lambda name: None,
        )
        assert data.topics[0].expected_hz == 30.0

    def test_unknown_msg_type(self) -> None:
        """A topic missing from topic_types is unknown."""
        timestamps = [i * 0.033 for i in range(30)]
        data = _build_timeline({"/foo": timestamps}, {})
        assert data.topics[0].msg_type == "unknown"

    def test_multi_topic_sorted_by_name(self) -> None:
        """Multiple topics are sorted by name."""
        data = _build_timeline(
            {
                "/zebra": [i * 0.01 for i in range(20)],
                "/alpha": [i * 0.01 for i in range(20)],
            },
            {},
        )
        names = [t.name for t in data.topics]
        assert names == ["/alpha", "/zebra"]

    def test_recording_start_ns_uses_min_timestamp(self) -> None:
        """recording_start_ns is the minimum of all timestamps, converted to ns."""
        timestamps = [100.5 + i * 0.033 for i in range(20)]
        data = _build_timeline({"/cam": timestamps}, {})
        # 100.5 sec * 1e9 = 100500000000 ns
        assert data.recording_start_ns == int(100.5 * 1e9)

    def test_log_time_offset_ns_zero_when_unspecified(self) -> None:
        """Offset is 0 when log_time_min_ns is not specified."""
        timestamps = [i * 0.033 for i in range(20)]
        data = _build_timeline({"/cam": timestamps}, {})
        assert data.log_time_offset_ns == 0

    def test_log_time_offset_ns_with_clock_skew(self) -> None:
        """When log_time_min_ns is given, the offset is computed.

        Case where the robot-side header.stamp is 60 days off because NTP is not synchronized.
        """
        # header.stamp starts at 100.0 sec
        timestamps = [100.0 + i * 0.033 for i in range(20)]
        # The minimum log_time is 60 days ahead of header.stamp
        log_time_min_ns = int((100.0 + 60 * 86400) * 1e9)
        data = _build_timeline({"/cam": timestamps}, {}, log_time_min_ns=log_time_min_ns)
        assert data.recording_start_ns == int(100.0 * 1e9)
        # Offset = 60 days worth
        assert data.log_time_offset_ns == int(60 * 86400 * 1e9)

    def test_log_time_offset_zero_when_log_time_min_is_zero(self) -> None:
        """Offset is 0 (fallback) when log_time_min_ns is 0."""
        timestamps = [i * 0.033 for i in range(20)]
        data = _build_timeline({"/cam": timestamps}, {}, log_time_min_ns=0)
        assert data.log_time_offset_ns == 0

    def test_edge_loss_added_to_gaps(self) -> None:
        """Leading/trailing blanks are added as gaps."""
        # 30 Hz, 10 s total length with the first 1 s blank
        timestamps = [1.0 + i * 0.033 for i in range(270)]
        # Add a second topic to extend the overall duration to the end
        data = _build_timeline(
            {
                "/cam": timestamps,
                "/joint": [i * 0.005 for i in range(2000)],  # 0-10 s
            },
            {},
        )
        cam_topic = next(t for t in data.topics if t.name == "/cam")
        # The leading blank is recorded as a gap
        assert any(g.start_sec == 0.0 for g in cam_topic.gaps)

    def test_bin_count_matches_duration(self) -> None:
        """Bin count is computed correctly from duration and bin_width."""
        timestamps = [i * 0.033 for i in range(60)]  # ~2 s
        data = _build_timeline({"/cam": timestamps}, {})
        topic = data.topics[0]
        # At bin_width=0.05 and 2 s, that's 40 bins
        assert len(topic.bins) >= 30

    def test_minor_loss_marked_in_bin(self) -> None:
        """A minor 1-2 frame loss is reflected as has_minor_loss."""
        # 30 Hz, 30 samples; insert ~0.06 s (2 frames lost) between indices 10 and 11
        timestamps = [i * 0.033 for i in range(30)]
        timestamps[11:] = [t + 0.06 for t in timestamps[11:]]
        # Add another topic to keep the overall duration aligned (to avoid emitting edge loss)
        data = _build_timeline(
            {
                "/cam": timestamps,
                "/joint": [i * 0.005 for i in range(int((max(timestamps) + 0.005) / 0.005))],
            },
            {},
        )
        cam_topic = next(t for t in data.topics if t.name == "/cam")
        # At least one bin has has_minor_loss=True
        assert any(b.has_minor_loss and not b.has_gap for b in cam_topic.bins)

    def test_gaps_sorted_by_start_sec(self) -> None:
        """gaps are sorted by start_sec ascending (preserved even when edge loss coexists with intermediate gaps).

        Regression: edge_events used to be prepended, so end_early would appear before
        intermediate gaps, breaking the UI display order.
        """
        # 30 Hz, 10 s recording. 1 s start_delay + 1 intermediate gap (~7 s mark) + ~1.5 s end_early
        interval = 1 / 30.0
        timestamps = [1.0 + i * interval for i in range(180)]  # 1.0 to ~7.0 s
        # Insert a 0.2 s gap after ~7.0 s
        timestamps += [7.2 + i * interval for i in range(30)]  # 7.2 to ~8.2 s
        # Extend the overall length to 10 s with another topic
        data = _build_timeline(
            {
                "/cam": timestamps,
                "/joint": [i * 0.005 for i in range(2000)],  # 0-10 s
            },
            {},
        )
        cam_topic = next(t for t in data.topics if t.name == "/cam")
        # There should be at least 3 gaps (start_delay / intermediate / end_early)
        assert len(cam_topic.gaps) >= 3
        # start_sec should be sorted ascending
        starts = [g.start_sec for g in cam_topic.gaps]
        assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# load_timeline
# ---------------------------------------------------------------------------


class TestLoadTimeline:
    """Tests for load_timeline()."""

    def test_no_cache_file(self, tmp_path: Path) -> None:
        """Returns None when there is no cache file."""
        assert load_timeline(tmp_path) is None

    def test_valid_cache(self, tmp_path: Path) -> None:
        """A valid cache is loaded as TimelineData."""
        cache = {
            "duration_sec": 10.0,
            "bin_width_sec": 0.05,
            "recording_start_ns": 1700000000000000000,
            "log_time_offset_ns": 0,
            "topics": [],
        }
        (tmp_path / "timeline_data.json").write_text(json.dumps(cache))
        result = load_timeline(tmp_path)
        assert result is not None
        assert result.duration_sec == 10.0
        assert result.recording_start_ns == 1700000000000000000

    def test_legacy_cache_without_new_fields(self, tmp_path: Path) -> None:
        """A legacy cache (without recording_start_ns / log_time_offset_ns) is treated as invalid and returns None (regenerated)."""
        cache = {
            "duration_sec": 10.0,
            "bin_width_sec": 0.05,
            "topics": [],
        }
        (tmp_path / "timeline_data.json").write_text(json.dumps(cache))
        result = load_timeline(tmp_path)
        assert result is None

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Broken JSON logs a warning and returns None."""
        (tmp_path / "timeline_data.json").write_text("not a json {{{")
        assert load_timeline(tmp_path) is None

    def test_invalid_schema(self, tmp_path: Path) -> None:
        """Schema mismatch returns None."""
        (tmp_path / "timeline_data.json").write_text(json.dumps({"foo": "bar"}))
        assert load_timeline(tmp_path) is None


# ---------------------------------------------------------------------------
# TimelineAnalyzer (lifecycle management)
# ---------------------------------------------------------------------------


class TestTimelineAnalyzer:
    """Tests for TimelineAnalyzer.get() / start()."""

    @pytest.mark.asyncio
    async def test_returns_cached_data(self, tmp_path: Path) -> None:
        """Returns immediately with ready when cached data is available."""
        cache = {
            "duration_sec": 10.0,
            "bin_width_sec": 0.05,
            "recording_start_ns": 1700000000000000000,
            "log_time_offset_ns": 0,
            "topics": [],
        }
        (tmp_path / "timeline_data.json").write_text(json.dumps(cache))

        analyzer = TimelineAnalyzer()
        result = await analyzer.get(tmp_path)
        assert result["status"] == "ready"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_no_mcap_returns_not_found(self, tmp_path: Path) -> None:
        """Returns not_found when there is no MCAP file."""
        with patch("app.features.jobs.service.get_job_queue") as mock_queue_fn:
            mock_queue = MagicMock()
            mock_queue.get_active_timeline_job.return_value = None
            mock_queue_fn.return_value = mock_queue
            analyzer = TimelineAnalyzer()
            result = await analyzer.get(tmp_path)
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_active_running_job_returns_analyzing(self, tmp_path: Path) -> None:
        """Returns analyzing when there is already a RUNNING job."""
        from app.features.jobs.models import JobStatus

        (tmp_path / "data.mcap").write_bytes(b"")  # An empty file is fine
        with patch("app.features.jobs.service.get_job_queue") as mock_queue_fn:
            mock_queue = MagicMock()
            active_job = MagicMock(status=JobStatus.RUNNING)
            mock_queue.get_active_timeline_job.return_value = active_job
            mock_queue_fn.return_value = mock_queue
            analyzer = TimelineAnalyzer()
            result = await analyzer.get(tmp_path)
        assert result["status"] == "analyzing"

    @pytest.mark.asyncio
    async def test_active_failed_job_returns_error(self, tmp_path: Path) -> None:
        """Returns an error when there is a failed job."""
        from app.features.jobs.models import JobStatus

        (tmp_path / "data.mcap").write_bytes(b"")
        with patch("app.features.jobs.service.get_job_queue") as mock_queue_fn:
            mock_queue = MagicMock()
            failed_job = MagicMock(status=JobStatus.FAILED, error="generation failed")
            mock_queue.get_active_timeline_job.return_value = failed_job
            mock_queue_fn.return_value = mock_queue
            analyzer = TimelineAnalyzer()
            result = await analyzer.get(tmp_path)
        assert result["status"] == "error"
        assert result["error"] == "generation failed"

    @pytest.mark.asyncio
    async def test_failed_job_without_error_message(self, tmp_path: Path) -> None:
        """Returns a default message when the failed job has no error message."""
        from app.features.jobs.models import JobStatus

        (tmp_path / "data.mcap").write_bytes(b"")
        with patch("app.features.jobs.service.get_job_queue") as mock_queue_fn:
            mock_queue = MagicMock()
            failed_job = MagicMock(status=JobStatus.FAILED, error=None)
            mock_queue.get_active_timeline_job.return_value = failed_job
            mock_queue_fn.return_value = mock_queue
            analyzer = TimelineAnalyzer()
            result = await analyzer.get(tmp_path)
        assert result["status"] == "error"
        assert "failed" in str(result["error"]).lower()

    @pytest.mark.asyncio
    async def test_start_enqueues_when_no_cache(self, tmp_path: Path) -> None:
        """start() enqueues when there is no cache but an MCAP is present."""
        (tmp_path / "data.mcap").write_bytes(b"")
        with patch("app.features.jobs.service.get_job_queue") as mock_queue_fn:
            mock_queue = MagicMock()
            mock_queue.get_active_timeline_job.return_value = None
            mock_queue.enqueue_timeline = AsyncMock()
            mock_queue_fn.return_value = mock_queue
            analyzer = TimelineAnalyzer()
            result = await analyzer.start(tmp_path)
        assert result["status"] == "analyzing"
        mock_queue.enqueue_timeline.assert_awaited_once_with(tmp_path)

    @pytest.mark.asyncio
    async def test_start_returns_cached_data(self, tmp_path: Path) -> None:
        """start() returns ready immediately when cached data is present."""
        cache = {
            "duration_sec": 10.0,
            "bin_width_sec": 0.05,
            "recording_start_ns": 1700000000000000000,
            "log_time_offset_ns": 0,
            "topics": [],
        }
        (tmp_path / "timeline_data.json").write_text(json.dumps(cache))
        result = await TimelineAnalyzer().start(tmp_path)
        assert result["status"] == "ready"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_start_active_failed_job_returns_error(self, tmp_path: Path) -> None:
        """start() surfaces a failed job's error."""
        from app.features.jobs.models import JobStatus

        (tmp_path / "data.mcap").write_bytes(b"")
        with patch("app.features.jobs.service.get_job_queue") as mock_queue_fn:
            mock_queue = MagicMock()
            mock_queue.get_active_timeline_job.return_value = MagicMock(status=JobStatus.FAILED, error="bad")
            mock_queue_fn.return_value = mock_queue
            result = await TimelineAnalyzer().start(tmp_path)
        assert result["status"] == "error"
        assert result["error"] == "bad"

    @pytest.mark.asyncio
    async def test_start_active_running_job_returns_analyzing(self, tmp_path: Path) -> None:
        """start() returns analyzing when a job is already running."""
        from app.features.jobs.models import JobStatus

        (tmp_path / "data.mcap").write_bytes(b"")
        with patch("app.features.jobs.service.get_job_queue") as mock_queue_fn:
            mock_queue = MagicMock()
            mock_queue.get_active_timeline_job.return_value = MagicMock(status=JobStatus.RUNNING)
            mock_queue_fn.return_value = mock_queue
            result = await TimelineAnalyzer().start(tmp_path)
        assert result["status"] == "analyzing"

    @pytest.mark.asyncio
    async def test_start_no_mcap_returns_not_found(self, tmp_path: Path) -> None:
        """start() returns not_found when there is no MCAP and no active job."""
        with patch("app.features.jobs.service.get_job_queue") as mock_queue_fn:
            mock_queue = MagicMock()
            mock_queue.get_active_timeline_job.return_value = None
            mock_queue_fn.return_value = mock_queue
            result = await TimelineAnalyzer().start(tmp_path)
        assert result["status"] == "not_found"
