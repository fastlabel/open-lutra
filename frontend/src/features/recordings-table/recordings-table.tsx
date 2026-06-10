/** Recordings table: GitHub Issues-style two-line list + search + filter + bulk actions.
 *
 * Ordering: always descending by recording start time (the backend's scan_output_dir
 * returns recording_start_ns desc + mtime fallback).
 * Filters: single-select dropdown by task_name.
 * Application order: search → taskFilter (AND-combined).
 */

import { Search } from "lucide-react";
import type { FileEntry } from "@/api/generated/schemas";
import { Checkbox } from "@/components/ui/checkbox";
import { BulkExportButton } from "@/features/lerobot-export";
import { BulkDeleteButton, RecordingListItem, useRecordingsStore } from "@/features/recordings";
import { useRecordingsTableStore } from "./store";
import { TaskFilter } from "./ui/task-filter";
import { applySearchAndFilter } from "./utils";

export function RecordingsTable({ entries }: { entries: FileEntry[] }) {
  const checkedFolders = useRecordingsStore((s) => s.checkedFolders);
  const toggleCheckAll = useRecordingsStore((s) => s.toggleCheckAll);
  const setCheckedFolders = useRecordingsStore((s) => s.setCheckedFolders);
  const searchText = useRecordingsTableStore((s) => s.searchText);
  const setSearchText = useRecordingsTableStore((s) => s.setSearchText);
  const taskFilter = useRecordingsTableStore((s) => s.taskFilter);
  const setTaskFilter = useRecordingsTableStore((s) => s.setTaskFilter);

  // List with only the search applied. Used as the population for TaskFilter options/counts.
  const searchedEntries = applySearchAndFilter(entries, searchText);

  // Final list with all filters applied
  const filteredEntries = applySearchAndFilter(entries, searchText, taskFilter);

  const allFolders = filteredEntries.map((e) => e.name);

  return (
    <div className="flex h-full flex-col">
      {/* Search bar */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-1.5">
        <Search size={14} className="shrink-0 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search by filename..."
          value={searchText}
          onChange={(e) => {
            const newSearchText = e.target.value;
            setCheckedFolders(
              newSearchText ? applySearchAndFilter(entries, newSearchText, taskFilter).map((x) => x.name) : [],
            );
            setSearchText(newSearchText);
          }}
          className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>

      {/* Select-all + filter + action row */}
      <div className="flex h-9 items-center justify-between border-b border-border bg-muted/30 px-4 text-xs">
        <div className="flex items-center gap-3">
          <Checkbox
            checked={allFolders.length > 0 && allFolders.every((f) => checkedFolders.has(f))}
            onCheckedChange={() => toggleCheckAll(allFolders)}
            aria-label="Select all"
          />
          <span className="text-muted-foreground tabular-nums">{filteredEntries.length}</span>
          <span className="mx-1 h-3 w-px bg-border" />
          <TaskFilter
            entries={searchedEntries}
            value={taskFilter}
            onChange={(newTaskFilter) => {
              setCheckedFolders(
                newTaskFilter === null
                  ? []
                  : applySearchAndFilter(entries, searchText, newTaskFilter).map((e) => e.name),
              );
              setTaskFilter(newTaskFilter);
            }}
          />
        </div>
        <div className="flex items-center gap-1">
          <BulkExportButton />
          <BulkDeleteButton />
        </div>
      </div>

      {/* List body */}
      <div className="flex-1 overflow-auto">
        {filteredEntries.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            {searchText ? "No matching files" : "No recordings yet"}
          </div>
        ) : (
          filteredEntries.map((entry) => <RecordingListItem key={entry.name} entry={entry} />)
        )}
      </div>
    </div>
  );
}
