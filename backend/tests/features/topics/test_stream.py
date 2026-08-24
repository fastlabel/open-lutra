"""Unit tests for the topic-stats SSE diff computation."""

from typing import Any

from app.features.topics.schemas import DiscoveredTopic, TopicInfo
from app.features.topics.stream import SNAPSHOT_INTERVAL_TICKS, TopicStreamDiffer, build_topic_rows


def _row(name: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "name": name,
        "msg_type": "std_msgs/msg/String",
        "actual_hz": 0,
        "status": "inactive",
        "message_count": 0,
        "is_subscribed": False,
    }
    row.update(overrides)
    return row


class TestBuildTopicRows:
    """Tests for build_topic_rows()."""

    def test_merges_stats_and_discovered(self) -> None:
        """Subscribed stats come first, discovered topics follow as inactive rows."""
        stats = [
            TopicInfo(
                name="/joint_states",
                msg_type="sensor_msgs/msg/JointState",
                actual_hz=99.3,
                status="ok",
                message_count=5230,
                is_subscribed=True,
                baseline_hz=100.0,
                baseline_fixed=True,
                loss_rate=0.0,
                drop_count=0,
                continuity_score=1.0,
                qos_reliability="RELIABLE",
            ),
        ]
        discovered = [DiscoveredTopic(name="/idle", msg_type="std_msgs/msg/String", is_subscribed=False)]

        rows = build_topic_rows(stats, discovered)

        assert [r["name"] for r in rows] == ["/joint_states", "/idle"]
        assert rows[0]["is_subscribed"] is True
        assert rows[0]["baseline_hz"] == 100.0
        assert rows[1] == _row("/idle")

    def test_empty_inputs(self) -> None:
        assert build_topic_rows([], []) == []


class TestTopicStreamDiffer:
    """Tests for TopicStreamDiffer.next_event()."""

    def test_first_tick_is_snapshot(self) -> None:
        differ = TopicStreamDiffer()
        rows = [_row("/a")]
        assert differ.next_event(rows) == ("topic_stats", rows)

    def test_unchanged_tick_yields_empty_delta(self) -> None:
        differ = TopicStreamDiffer()
        rows = [_row("/a"), _row("/b")]
        differ.next_event(rows)
        assert differ.next_event([_row("/a"), _row("/b")]) == (
            "topic_stats_delta",
            {"changed": [], "removed": []},
        )

    def test_changed_row_appears_in_delta(self) -> None:
        differ = TopicStreamDiffer()
        differ.next_event([_row("/a"), _row("/b")])
        changed = _row("/a", actual_hz=10.0, status="ok")
        event_name, payload = differ.next_event([changed, _row("/b")])
        assert event_name == "topic_stats_delta"
        assert payload == {"changed": [changed], "removed": []}

    def test_new_row_appears_in_delta(self) -> None:
        differ = TopicStreamDiffer()
        differ.next_event([_row("/a")])
        event_name, payload = differ.next_event([_row("/a"), _row("/new")])
        assert event_name == "topic_stats_delta"
        assert payload == {"changed": [_row("/new")], "removed": []}

    def test_removed_row_appears_in_delta(self) -> None:
        differ = TopicStreamDiffer()
        differ.next_event([_row("/a"), _row("/gone")])
        event_name, payload = differ.next_event([_row("/a")])
        assert event_name == "topic_stats_delta"
        assert payload == {"changed": [], "removed": ["/gone"]}

    def test_snapshot_repeats_every_interval(self) -> None:
        differ = TopicStreamDiffer(snapshot_interval=3)
        rows = [_row("/a")]
        assert differ.next_event(rows)[0] == "topic_stats"
        assert differ.next_event(rows)[0] == "topic_stats_delta"
        assert differ.next_event(rows)[0] == "topic_stats_delta"
        assert differ.next_event(rows)[0] == "topic_stats"

    def test_delta_after_snapshot_diffs_against_snapshot(self) -> None:
        """A snapshot resets the comparison base, so the next delta is relative to it."""
        differ = TopicStreamDiffer(snapshot_interval=2)
        differ.next_event([_row("/a")])  # snapshot
        differ.next_event([_row("/a"), _row("/b")])  # delta: /b new
        differ.next_event([_row("/a"), _row("/b")])  # snapshot
        event_name, payload = differ.next_event([_row("/a"), _row("/b")])
        assert event_name == "topic_stats_delta"
        assert payload == {"changed": [], "removed": []}

    def test_default_interval_matches_constant(self) -> None:
        differ = TopicStreamDiffer()
        rows = [_row("/a")]
        events = [differ.next_event(rows)[0] for _ in range(SNAPSHOT_INTERVAL_TICKS + 1)]
        assert events[0] == "topic_stats"
        assert all(e == "topic_stats_delta" for e in events[1:SNAPSHOT_INTERVAL_TICKS])
        assert events[SNAPSHOT_INTERVAL_TICKS] == "topic_stats"
