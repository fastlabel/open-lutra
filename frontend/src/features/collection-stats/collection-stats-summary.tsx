/** "Today's collection" button for the app header, opening a dialog that breaks today's recordings down by
 * validation result: OK (`pass` / `warn`, with their total duration), failed, validation error, no result, and the
 * total. "No result" covers both validation still running and validation that never produced a result (for example
 * a failed validation job).
 *
 * Hidden entirely unless the recording config enables `collection_stats` (exposed as
 * `collection_stats_enabled` on `/api/config`). Today's recordings are fetched only while the dialog is open, and
 * again each time it opens.
 */

import { CalendarCheck } from "lucide-react";
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useConfig, useFiles } from "@/hooks/use-api";
import { localDayRange } from "./day-range";
import { formatCollectedDuration } from "./format";
import { summarize } from "./summarize";
import { BreakdownRow } from "./ui/breakdown-row";

export function CollectionStatsSummary() {
  // --- Server state ---
  const { data: config } = useConfig();

  if (!config?.collection_stats_enabled) return null;

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded px-1.5 py-1 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <CalendarCheck size={14} />
          <span>Today's collection</span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Today's collection</DialogTitle>
          <DialogDescription>Recordings started today, by validation result.</DialogDescription>
        </DialogHeader>
        <TodayBreakdown />
      </DialogContent>
    </Dialog>
  );
}

/** Mounted only while the dialog is open, so the recordings request is issued on open, not with the header. */
function TodayBreakdown() {
  // --- Server state ---
  // "Today" is fixed when the dialog opens, so a re-render after midnight does not switch it to the next day.
  const [range] = useState(() => localDayRange(new Date()));
  const { data, isError } = useFiles(range);

  if (isError) return <p className="text-[13px] text-red-400">Could not load today's recordings.</p>;
  if (!data) return <p className="text-[13px] text-muted-foreground">Loading…</p>;

  const summary = summarize(data.entries);

  return (
    <div className="mt-2 flex flex-col gap-2 text-[13px]">
      <BreakdownRow
        label="OK (pass / warn)"
        count={summary.usable.count}
        duration={formatCollectedDuration(summary.usable.durationNs / 1e9)}
        dotClass="bg-emerald-400"
      />
      <BreakdownRow label="Failed" count={summary.failed} dotClass="bg-red-400" />
      {summary.errors > 0 && <BreakdownRow label="Validation error" count={summary.errors} dotClass="bg-purple-400" />}
      <BreakdownRow label="No result" count={summary.pending} dotClass="bg-muted-foreground" />
      <div className="border-t border-border pt-2">
        <BreakdownRow label="Total recorded" count={summary.total} />
      </div>
    </div>
  );
}
