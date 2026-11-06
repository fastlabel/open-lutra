/** Today's collection chip for the recording bar, with a popover that breaks the day down by validation result.
 *
 * The chip shows only OK episodes (validation `pass` / `warn`) and their duration; a red dot flags failed or
 * errored takes. The popover lists OK / failed / validation error / checking (no result yet) and the total.
 *
 * Hidden entirely unless the recording config enables `collection_stats` (exposed as
 * `collection_stats_enabled` on `/api/config`). The recordings query lives in the inner component, so a
 * disabled deployment issues no extra request.
 */

import { CalendarCheck, ChevronDown } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useConfig, useFiles } from "@/hooks/use-api";
import { localDayRange } from "./day-range";
import { formatCollectedDuration, formatEpisodes } from "./format";
import { summarize } from "./summarize";
import { BreakdownRow } from "./ui/breakdown-row";
import { useLocalDay } from "./use-local-day";

export function CollectionStatsSummary() {
  // --- Server state ---
  const { data: config } = useConfig();

  if (!config?.collection_stats_enabled) return null;
  return <TodaySummary />;
}

function TodaySummary() {
  // --- Server state ---
  const today = useLocalDay();
  const { data } = useFiles(localDayRange(today));

  if (!data) return null;

  const summary = summarize(data.entries);
  const okDuration = formatCollectedDuration(summary.usable.durationNs / 1e9);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          title="Episodes that passed validation today (click for details)"
          className="flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-1 text-[13px] text-foreground hover:bg-muted"
        >
          <CalendarCheck size={14} className="text-emerald-400" />
          <span className="text-muted-foreground">Today</span>
          <span className="font-semibold tabular-nums">
            {formatEpisodes(summary.usable.count)} · {okDuration}
          </span>
          {summary.failed + summary.errors > 0 && (
            <span className="h-2 w-2 rounded-full bg-red-400" title="Some takes failed" />
          )}
          <ChevronDown size={13} className="text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-3">
        <div className="flex flex-col gap-2 text-[13px]">
          <span className="font-medium text-muted-foreground">Today's collection</span>
          <BreakdownRow
            label="OK (pass / warn)"
            count={summary.usable.count}
            duration={okDuration}
            dotClass="bg-emerald-400"
          />
          <BreakdownRow label="Failed" count={summary.failed} dotClass="bg-red-400" />
          {summary.errors > 0 && (
            <BreakdownRow label="Validation error" count={summary.errors} dotClass="bg-amber-400" />
          )}
          <BreakdownRow label="Checking" count={summary.pending} dotClass="bg-muted-foreground" />
          <div className="border-t border-border pt-2">
            <BreakdownRow label="Total recorded" count={summary.total} />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
