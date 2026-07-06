/** Previous/next recording computation for the detail page's pager.
 *
 * The pager walks the same sequence the user was viewing on the list: the filtered
 * list when the current recording is part of it, otherwise the full list (so the
 * pager still works when the current recording is excluded by the active filter, or
 * when the detail page was opened via a deep link with no filter context).
 */

import type { FileEntry } from "@/api/generated/schemas";

export interface RecordingNeighbors {
  prev: FileEntry | null;
  next: FileEntry | null;
  /** Position of the current recording within the sequence (-1 when it is absent). */
  index: number;
  /** Length of the sequence the pager walks. */
  total: number;
  /** Whether the current recording exists in the full list. False → deleted or never existed. */
  currentExists: boolean;
}

export function computeNeighbors(entries: FileEntry[], filtered: FileEntry[], currentPath: string): RecordingNeighbors {
  const filteredIndex = filtered.findIndex((e) => e.path === currentPath);
  // Walk the filtered list when the current recording is in it; otherwise fall back to the full list.
  const sequence = filteredIndex >= 0 ? filtered : entries;
  const index = filteredIndex >= 0 ? filteredIndex : entries.findIndex((e) => e.path === currentPath);
  return {
    prev: index > 0 ? sequence[index - 1] : null,
    next: index >= 0 && index < sequence.length - 1 ? sequence[index + 1] : null,
    index,
    total: sequence.length,
    currentExists: index >= 0,
  };
}
