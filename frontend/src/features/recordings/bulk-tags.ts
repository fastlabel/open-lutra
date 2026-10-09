/** Tag bookkeeping for the bulk edit dialog: which tags the selected recordings carry and what a click changes. */

import type { FileEntry } from "@/api/generated/schemas";

/** How widely a tag is present across the selected recordings before any edit. */
export type TagPresence = "all" | "some" | "none";

/** Checkbox state of a tag row. `mixed` only occurs for tags present on some of the recordings. */
export type TagCheck = "checked" | "mixed" | "unchecked";

export interface TagRow {
  tag: string;
  /** Number of selected recordings that carry the tag. */
  count: number;
  presence: TagPresence;
  check: TagCheck;
}

/** One row per tag found on the entries, most common first (ties by name).
 *
 * `total` is the number of selected recordings: a tag is checked only when it is on that many, so a selected
 * recording missing from `entries` keeps its tags shown as mixed rather than as on all of them.
 */
export function buildTagRows(entries: FileEntry[], total: number): TagRow[] {
  const counts = new Map<string, number>();
  for (const entry of entries) {
    for (const tag of new Set(entry.tags)) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([tagA, countA], [tagB, countB]) => countB - countA || tagA.localeCompare(tagB))
    .map(([tag, count]) => {
      const presence: TagPresence = count === total ? "all" : "some";
      return {
        tag,
        count,
        presence,
        check: presence === "all" ? "checked" : "mixed",
      };
    });
}

/** A tag typed by the operator: on none of the recordings yet, and checked so that saving adds it. */
export function newTagRow(tag: string): TagRow {
  return { tag, count: 0, presence: "none", check: "checked" };
}

/** The rows with `tag` checked: an existing row is checked in place, any other tag is appended as a new row. */
export function withTagChecked(rows: TagRow[], tag: string): TagRow[] {
  return rows.some((row) => row.tag === tag)
    ? rows.map((row) => (row.tag === tag ? { ...row, check: "checked" } : row))
    : [...rows, newTagRow(tag)];
}

/** The state after a click: rows on some recordings cycle mixed → checked → unchecked → mixed; every other row toggles. */
export function cycleTagCheck(row: TagRow): TagCheck {
  if (row.presence === "some") {
    if (row.check === "mixed") return "checked";
    return row.check === "checked" ? "unchecked" : "mixed";
  }
  return row.check === "checked" ? "unchecked" : "checked";
}

/** What saving the row does: add the tag to every selected recording, remove it from every one, or nothing. */
export function tagDelta(row: TagRow): "add" | "remove" | null {
  if (row.check === "checked" && row.presence !== "all") return "add";
  if (row.check === "unchecked" && row.presence !== "none") return "remove";
  return null;
}

/** The tag fields of the bulk update request, in row order. */
export function tagRequest(rows: TagRow[]): {
  add_tags: string[];
  remove_tags: string[];
} {
  return {
    add_tags: rows.filter((row) => tagDelta(row) === "add").map((row) => row.tag),
    remove_tags: rows.filter((row) => tagDelta(row) === "remove").map((row) => row.tag),
  };
}
