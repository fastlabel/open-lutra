/** Merging logic for `topic_stats` SSE events.
 *
 * Each event carries only the rows that changed since the previous event on
 * the connection; the first event after a (re)connect carries every row and
 * replaces the list instead (see docs/domain/sse.md).
 */

import type { TopicInfo } from "@/api/generated/schemas";

/** Merge the changed rows of one event into the previous full row list.
 *
 * Unchanged rows keep their object identity so memoized row components can
 * skip re-rendering; rows first seen here are appended (display order is
 * imposed by the consumer's sort, not by this list).
 */
export function upsertTopicStats(prev: TopicInfo[], changed: TopicInfo[]): TopicInfo[] {
  if (changed.length === 0) return prev;

  const changedByName = new Map(changed.map((t) => [t.name, t]));
  const merged = prev.map((row) => {
    const next = changedByName.get(row.name);
    if (!next) return row;
    changedByName.delete(row.name);
    return next;
  });
  merged.push(...changedByName.values());
  return merged;
}
