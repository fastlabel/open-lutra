/** Resolves the previous/next recording for the detail page pager from the cached list.
 *
 * Reuses the `useFiles` query cache (already warm when navigating from the list) and the
 * same `applySearchAndFilter` the list uses, so the pager order matches what the user saw.
 */

import { useMemo } from "react";
import { useFiles } from "@/hooks/use-api";
import { computeNeighbors, type RecordingNeighbors } from "./neighbors";
import { applySearchAndFilter, type TaskFilterValue } from "./utils";

export function useRecordingNeighbors(
  currentPath: string,
  searchText: string,
  taskFilter: TaskFilterValue,
): RecordingNeighbors & { isLoaded: boolean } {
  const { data, isSuccess } = useFiles();
  const entries = useMemo(() => data?.entries ?? [], [data]);
  const filtered = useMemo(
    () => applySearchAndFilter(entries, searchText, taskFilter),
    [entries, searchText, taskFilter],
  );
  const neighbors = useMemo(() => computeNeighbors(entries, filtered, currentPath), [entries, filtered, currentPath]);
  return { ...neighbors, isLoaded: isSuccess };
}
