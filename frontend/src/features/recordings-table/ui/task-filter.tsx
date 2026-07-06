/** Dropdown filter by task_name.
 *
 * - Single-select (clicking the current selection again resets to "All")
 * - Options are aggregated as unique task_names from the `entries` argument (= post-search list)
 * - Tasks with count 0 are not shown. "(no task)" appears only if there are recordings without task_name
 * - Stateless: the selection is owned by the caller (backed by URL search params)
 */

import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";
import type { FileEntry } from "@/api/generated/schemas";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { TaskFilterValue } from "../utils";

const ALL_LABEL = "All";
const NONE_LABEL = "(no task)";

interface TaskFilterProps {
  /** Source of aggregation. Pass post-search entries so counts track the current view. */
  entries: FileEntry[];
  value: TaskFilterValue;
  onChange: (value: TaskFilterValue) => void;
}

export function TaskFilter({ entries, value, onChange }: TaskFilterProps) {
  const [open, setOpen] = useState(false);

  const { named, noneCount } = useMemo(() => {
    const counts = new Map<string, number>();
    let noneCount = 0;
    for (const e of entries) {
      if (e.task_name) counts.set(e.task_name, (counts.get(e.task_name) ?? 0) + 1);
      else noneCount++;
    }
    return {
      named: [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)),
      noneCount,
    };
  }, [entries]);

  const triggerLabel = value === null ? ALL_LABEL : value === "" ? NONE_LABEL : value;
  const isActive = value !== null;

  // Re-selecting the same item resets to "All".
  const select = (next: TaskFilterValue) => {
    onChange(next !== null && next === value ? null : next);
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs transition-colors ${
            isActive ? "bg-foreground/10 text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
          }`}
        >
          <span className="max-w-[160px] truncate">Task: {triggerLabel}</span>
          <ChevronDown size={12} />
        </button>
      </PopoverTrigger>
      <PopoverContent className="min-w-[200px] max-h-72 overflow-auto">
        <TaskOption label={ALL_LABEL} count={entries.length} active={value === null} onClick={() => select(null)} />
        {noneCount > 0 && (
          <TaskOption label={NONE_LABEL} count={noneCount} active={value === ""} onClick={() => select("")} />
        )}
        {named.map(([name, count]) => (
          <TaskOption key={name} label={name} count={count} active={value === name} onClick={() => select(name)} />
        ))}
      </PopoverContent>
    </Popover>
  );
}

function TaskOption({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-xs ${
        active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"
      }`}
    >
      <span className="truncate" title={label}>
        {label}
      </span>
      <span className="shrink-0 tabular-nums text-[11px]">{count}</span>
    </button>
  );
}
