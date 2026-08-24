/** Merging logic for `topic_stats_delta` SSE events.
 *
 * The stream sends a full `topic_stats` snapshot on connect and periodically;
 * in between, `topic_stats_delta` carries only the rows that changed plus the
 * names of rows that disappeared (see docs/domain/sse.md).
 */

import type { TopicInfo } from "@/api/generated/schemas";

/** Payload of a `topic_stats_delta` SSE event (outside OpenAPI, so not orval-generated). */
export interface TopicStatsDelta {
  /** Rows that differ from the previous tick, including newly discovered topics. */
  changed: TopicInfo[];
  /** Names of rows that vanished since the previous tick. */
  removed: string[];
}

/** Merge one delta into the previous full row list.
 *
 * Unchanged rows keep their object identity so memoized row components can
 * skip re-rendering; rows first seen in a delta are appended (display order
 * is imposed by the consumer's sort, not by this list).
 */
export function mergeTopicStatsDelta(prev: TopicInfo[], delta: TopicStatsDelta): TopicInfo[] {
  const changedByName = new Map(delta.changed.map((t) => [t.name, t]));
  const removed = new Set(delta.removed);

  const merged: TopicInfo[] = [];
  for (const row of prev) {
    if (removed.has(row.name)) continue;
    const next = changedByName.get(row.name);
    if (next) {
      merged.push(next);
      changedByName.delete(row.name);
    } else {
      merged.push(row);
    }
  }
  for (const row of changedByName.values()) {
    merged.push(row);
  }
  return merged;
}
