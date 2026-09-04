"""Unit tests for the topic-stats SSE diff computation."""

from typing import Any

from app.features.topics.schemas import DiscoveredTopic, TopicInfo
from app.features.topics.stream import TopicStreamDiffer


def _info(name: str, actual_hz: float = 99.3, status: str = "ok") -> TopicInfo:
    return TopicInfo(
        name=name,
        msg_type="sensor_msgs/msg/JointState",
        actual_hz=actual_hz,
        status=status,
        message_count=5230,
        is_subscribed=True,
        baseline_hz=100.0,
        baseline_fixed=True,
        loss_rate=0.0,
        drop_count=0,
        continuity_score=1.0,
        qos_reliability="RELIABLE",
    )


def _disc(name: str, msg_type: str = "std_msgs/msg/String") -> DiscoveredTopic:
    return DiscoveredTopic(name=name, msg_type=msg_type, is_subscribed=False)


def _disc_row(name: str, msg_type: str = "std_msgs/msg/String") -> dict[str, Any]:
    """The minimal inactive row a discovered topic is rendered as."""
    return {
        "name": name,
        "msg_type": msg_type,
        "actual_hz": 0,
        "status": "inactive",
        "message_count": 0,
        "is_subscribed": False,
    }


class TestTopicStreamDiffer:
    """Tests for TopicStreamDiffer.next_changed()."""

    def test_first_tick_returns_all_rows_stats_first(self) -> None:
        """The differ starts empty, so the first tick carries every merged row."""
        rows = TopicStreamDiffer().next_changed([_info("/joint_states")], [_disc("/idle")])

        assert [r["name"] for r in rows] == ["/joint_states", "/idle"]
        assert rows[0]["is_subscribed"] is True
        assert rows[0]["baseline_hz"] == 100.0
        assert rows[1] == _disc_row("/idle")

    def test_empty_inputs(self) -> None:
        assert TopicStreamDiffer().next_changed([], []) == []

    def test_unchanged_tick_returns_empty_list(self) -> None:
        differ = TopicStreamDiffer()
        differ.next_changed([_info("/a")], [_disc("/idle")])
        assert differ.next_changed([_info("/a")], [_disc("/idle")]) == []

    def test_changed_row_only(self) -> None:
        differ = TopicStreamDiffer()
        differ.next_changed([_info("/a")], [_disc("/idle")])

        changed = differ.next_changed([_info("/a", actual_hz=50.0, status="warning")], [_disc("/idle")])

        assert [r["name"] for r in changed] == ["/a"]
        assert changed[0]["actual_hz"] == 50.0

    def test_new_row_included(self) -> None:
        differ = TopicStreamDiffer()
        differ.next_changed([], [_disc("/a")])
        assert differ.next_changed([], [_disc("/a"), _disc("/new")]) == [_disc_row("/new")]

    def test_subscribing_a_discovered_topic_is_a_change(self) -> None:
        """A topic moving from discovered to subscribed changes its row shape."""
        differ = TopicStreamDiffer()
        differ.next_changed([], [_disc("/a")])

        changed = differ.next_changed([_info("/a")], [])

        assert [r["name"] for r in changed] == ["/a"]
        assert changed[0]["is_subscribed"] is True

    def test_diffs_against_previous_tick_not_first(self) -> None:
        """The comparison base advances every tick."""
        differ = TopicStreamDiffer()
        differ.next_changed([_info("/a")], [])
        differ.next_changed([_info("/a", actual_hz=50.0)], [])
        assert differ.next_changed([_info("/a", actual_hz=50.0)], []) == []
