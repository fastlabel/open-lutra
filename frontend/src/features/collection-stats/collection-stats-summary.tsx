/** Today's collection summary for the recording bar: usable episodes and duration, plus the total and its breakdown.
 *
 * Hidden entirely unless the recording config enables `collection_stats` (exposed as
 * `collection_stats_enabled` on `/api/config`). The recordings query lives in the inner component, so a
 * disabled deployment issues no extra request.
 */

import { CalendarCheck } from "lucide-react";
import { useConfig, useFiles } from "@/hooks/use-api";
import { formatDuration } from "@/lib/format";
import { localDayRange } from "./day-range";
import { summarize } from "./summarize";
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
  const breakdown = [
    { label: "failed", count: summary.failed, className: "text-red-400" },
    { label: "validation errors", count: summary.errors, className: "text-amber-400" },
    { label: "pending", count: summary.pending, className: "text-muted-foreground" },
  ].filter((item) => item.count > 0);

  return (
    <div className="flex flex-col justify-center gap-1" role="status" aria-label="Today's collection">
      <div className="flex items-center gap-1.5 text-[13px]">
        <CalendarCheck size={14} className="text-emerald-400" />
        <span className="font-medium text-muted-foreground">Today</span>
        <span className="font-semibold tabular-nums text-foreground">
          {summary.usable.count} usable · {formatDuration(summary.usable.durationNs / 1e9)}
        </span>
      </div>
      <span className="text-[13px] tabular-nums text-muted-foreground">
        {summary.total} total
        {breakdown.map((item) => (
          <span key={item.label} className={item.className}>
            {" "}
            · {item.count} {item.label}
          </span>
        ))}
      </span>
    </div>
  );
}
