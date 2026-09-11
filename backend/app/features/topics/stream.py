"""Diff computation for the topic-stats SSE stream.

The stream keeps the "one row per topic" contract of GET /api/topics, but
sending every row every second is redundant: idle rows are byte-identical
tick after tick. A per-connection ``TopicStreamDiffer`` therefore emits only
the rows that changed since the previous tick. The differ starts empty, so
the first event on a (re)connection naturally carries every row — the client
replaces its list there and merges afterwards.

Rows are never removed within a backend's lifetime: a topic whose publisher
vanished stays visible as an idle row (deliberately — "existed before, cannot
be measured now" is information). With no removals there is nothing for a
client to miss, so no "removed" channel and no snapshot/reset event exist.
"""

from typing import Any

from app.features.topics.schemas import DiscoveredTopic, TopicInfo


def _build_topic_rows(stats: list[TopicInfo], discovered: list[DiscoveredTopic]) -> list[dict[str, Any]]:
    """Merge subscribed stats and discovered-but-unsubscribed topics into one row list.

    Discovered topics carry no measurements yet, so they are rendered as
    minimal inactive rows (same shape the frontend has always received).
    """
    return [s.model_dump(mode="json") for s in stats] + [
        {
            "name": d.name,
            "msg_type": d.msg_type,
            "actual_hz": 0,
            "status": "inactive",
            "message_count": 0,
            "is_subscribed": False,
        }
        for d in discovered
    ]


class TopicStreamDiffer:
    """Per-connection state that reduces the full topic list to changed rows.

    ``next_changed`` is called once per tick with the monitor's subscribed
    stats and discovered topics, and returns the merged rows that differ from
    the previous tick: all rows on the first tick, and an empty list when
    nothing changed (still sent — the 1Hz tick doubles as a keep-alive and
    advances the client's quality history).
    """

    def __init__(self) -> None:
        self._last_rows: dict[str, dict[str, Any]] = {}

    def next_changed(self, stats: list[TopicInfo], discovered: list[DiscoveredTopic]) -> list[dict[str, Any]]:
        """Return the rows that changed since the previous tick and remember the new state."""
        rows = _build_topic_rows(stats, discovered)
        previous = self._last_rows
        self._last_rows = {row["name"]: row for row in rows}
        return [row for row in rows if previous.get(row["name"]) != row]
