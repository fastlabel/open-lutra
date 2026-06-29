/** Recordings table: GitHub Issues-style two-line list + search + filter + bulk actions.
 *
 * Ordering: always descending by recording start time (the backend's scan_output_dir
 * returns recording_start_ns desc + mtime fallback).
 * Filters: single-select dropdown by task_name.
 * Application order: search → taskFilter (AND-combined).
 *
 * The list body is virtualized (@tanstack/react-virtual): only the visible rows are
 * mounted, so a 1000+ recording list stays responsive.
 */

import { useVirtualizer } from "@tanstack/react-virtual";
import { Search } from "lucide-react";
import { useMemo, useRef } from "react";
import type { FileEntry } from "@/api/generated/schemas";
import { Checkbox } from "@/components/ui/checkbox";
import { BulkExportButton } from "@/features/lerobot-export";
import { BulkDeleteButton, RecordingListItem, useRecordingsStore } from "@/features/recordings";
import { BulkUploadButton } from "@/features/upload";
import { useRecordingsTableStore } from "./store";
import { TaskFilter } from "./ui/task-filter";
import { applySearchAndFilter } from "./utils";

export function RecordingsTable({ entries }: { entries: FileEntry[] }) {
  // --- Filter state + derived lists ---
  const searchText = useRecordingsTableStore((s) => s.searchText);
  const taskFilter = useRecordingsTableStore((s) => s.taskFilter);

  // List with only the search applied. Used as the population for TaskFilter options/counts.
  const searchedEntries = useMemo(() => applySearchAndFilter(entries, searchText), [entries, searchText]);
  // Final list with all filters applied.
  const filteredEntries = useMemo(
    () => applySearchAndFilter(entries, searchText, taskFilter),
    [entries, searchText, taskFilter],
  );
  const allFolders = useMemo(() => filteredEntries.map((e) => e.name), [filteredEntries]);

  // --- Virtualization ---
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: filteredEntries.length,
    getScrollElement: () => scrollRef.current,
    // Initial guess for a two-line row (py-2 padding + title + meta line + 1px border).
    // Only affects scrollbar sizing before each row is measured; measureElement corrects it.
    estimateSize: () => 57,
    // Render 8 extra rows above/below the viewport so fast scrolling does not flash blanks.
    overscan: 8,
  });

  // --- Render-only state ---
  const setSearchText = useRecordingsTableStore((s) => s.setSearchText);
  const setTaskFilter = useRecordingsTableStore((s) => s.setTaskFilter);
  const checkedFolders = useRecordingsStore((s) => s.checkedFolders);
  const toggleCheckAll = useRecordingsStore((s) => s.toggleCheckAll);
  const setCheckedFolders = useRecordingsStore((s) => s.setCheckedFolders);

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
          <BulkUploadButton />
          <BulkExportButton />
          <BulkDeleteButton />
        </div>
      </div>

      {/* List body (virtualized) */}
      <div ref={scrollRef} className="flex-1 overflow-auto">
        {filteredEntries.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            {searchText ? "No matching files" : "No recordings yet"}
          </div>
        ) : (
          <div className="relative w-full" style={{ height: virtualizer.getTotalSize() }}>
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const entry = filteredEntries[virtualRow.index];
              return (
                <div
                  key={entry.name}
                  data-index={virtualRow.index}
                  ref={virtualizer.measureElement}
                  className="absolute top-0 left-0 w-full"
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                >
                  <RecordingListItem entry={entry} />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
