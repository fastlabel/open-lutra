/** Utilities for the recordings table.
 *
 * MCAP folders are always shown in descending date order (the default of `scan_output_dir`),
 * so no client-side sort function is provided.
 */

import type { FileEntry } from "@/api/generated/schemas";

export { formatRecordingDate } from "@/lib/format";

/** Filter value by task_name.
 *
 * - `null`: all tasks (no filter)
 * - `""`: only recordings without a task_name
 * - any other string: only recordings whose task_name matches exactly
 */
export type TaskFilterValue = string | null;

/** Formats a byte count into a human-readable string. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)}GB`;
}

/** Applies the task_name filter. Returns input unchanged when null. */
export function applyTaskFilter(entries: FileEntry[], taskFilter: TaskFilterValue): FileEntry[] {
  if (taskFilter === null) return entries;
  if (taskFilter === "") return entries.filter((e) => !e.task_name);
  return entries.filter((e) => e.task_name === taskFilter);
}

/** Applies the search text and task filter in sequence (AND-combined). */
export function applySearchAndFilter(
  entries: FileEntry[],
  searchText: string,
  taskFilter: TaskFilterValue = null,
): FileEntry[] {
  let result = entries;
  if (searchText) {
    const needle = searchText.toLowerCase();
    result = result.filter((e) => e.name.toLowerCase().includes(needle));
  }
  result = applyTaskFilter(result, taskFilter);
  return result;
}
