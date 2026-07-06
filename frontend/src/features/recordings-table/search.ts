/** URL search-param schema for the recordings list and detail routes.
 *
 * The recordings filter lives entirely in the URL so it survives reloads, new tabs,
 * bookmarks, and carries into the detail page (which uses it to determine the
 * previous/next recording). Both `/recordings` and `/recordings/$folder` share this schema.
 *
 * `task` maps to a `TaskFilterValue`:
 * - omitted  → all tasks (no filter)
 * - `""`     → only recordings without a task_name
 * - a string → only recordings whose task_name matches exactly
 *
 * `q` (folder-name search) is omitted from the URL when empty to keep URLs clean.
 */

export interface RecordingsSearch {
  q?: string;
  task?: string;
}

/** Validate and normalize raw search params. Unknown / malformed values are dropped. */
export function validateRecordingsSearch(raw: Record<string, unknown>): RecordingsSearch {
  const out: RecordingsSearch = {};
  if (typeof raw.q === "string" && raw.q !== "") out.q = raw.q;
  if (typeof raw.task === "string") out.task = raw.task;
  return out;
}
