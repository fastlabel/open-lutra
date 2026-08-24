"""Diff computation for the topic-stats SSE stream.

The stream keeps the "one row per topic" contract of GET /api/topics, but
sending every row every second is redundant: idle rows are byte-identical
tick after tick. A per-connection ``TopicStreamDiffer`` therefore emits a
full snapshot periodically (and on connect) and, in between, only the rows
that changed plus the names of rows that disappeared.
"""

from typing import Any

from app.features.topics.schemas import DiscoveredTopic, TopicInfo

# Ticks between full snapshots (1 tick = 1 second in the SSE loop). Snapshots
# bound how long a client that missed a delta can stay stale.
SNAPSHOT_INTERVAL_TICKS = 10


def build_topic_rows(stats: list[TopicInfo], discovered: list[DiscoveredTopic]) -> list[dict[str, Any]]:
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
    """Per-connection state that turns full row lists into snapshot/delta events.

    ``next_event`` is called once per tick with the current full row list and
    returns ``(event_name, payload)``:

    - ``("topic_stats", rows)``: full snapshot — first tick and every
      ``SNAPSHOT_INTERVAL_TICKS`` ticks thereafter. The client replaces its
      whole list.
    - ``("topic_stats_delta", {"changed": rows, "removed": names})``: all other
      ticks. ``changed`` holds rows that differ from the previous tick
      (including brand-new topics); ``removed`` holds names of rows that
      vanished. The client merges into its list.
    """

    def __init__(self, snapshot_interval: int = SNAPSHOT_INTERVAL_TICKS) -> None:
        self._snapshot_interval = snapshot_interval
        self._tick = 0
        self._last_rows: dict[str, dict[str, Any]] = {}

    def next_event(self, rows: list[dict[str, Any]]) -> tuple[str, Any]:
        """Compute the SSE event for this tick and remember the rows for the next one."""
        current = {row["name"]: row for row in rows}
        is_snapshot = self._tick % self._snapshot_interval == 0
        self._tick += 1

        if is_snapshot:
            self._last_rows = current
            return ("topic_stats", rows)

        changed = [row for name, row in current.items() if self._last_rows.get(name) != row]
        removed = [name for name in self._last_rows if name not in current]
        self._last_rows = current
        return ("topic_stats_delta", {"changed": changed, "removed": removed})
