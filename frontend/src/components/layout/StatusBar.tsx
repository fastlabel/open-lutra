/** StatusBar (footer): displays connection status, memory, and REC indicator.
 *
 * Shown in dev mode only (gated by `isDevMode()` / `VITE_DEV_MODE` in `__root.tsx`)
 * since it is unnecessary for normal usage.
 */

import { MemoryStick } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useIsRecording, useMemory } from "@/hooks/use-api";
import { useJobs } from "@/hooks/use-jobs-stream";
import { type SseConnectionStatus, useConnectionStatus } from "@/hooks/use-topics-stream";
import { usePanelStore } from "@/stores/panel-store";
import { isInFlight, JobPill } from "./job-pill";

/** Dot color for each connection status. */
const statusDotClass: Record<SseConnectionStatus, string> = {
  connected: "bg-emerald-500",
  connecting: "bg-amber-500 animate-pulse",
  reconnecting: "bg-amber-500 animate-pulse",
  disconnected: "bg-red-500",
};

/** Label for each connection status. */
const statusLabel: Record<SseConnectionStatus, string> = {
  connected: "Connected",
  connecting: "Connecting...",
  reconnecting: "Reconnecting...",
  disconnected: "Disconnected",
};

/** Format a byte count as MB. */
function formatMB(bytes: number): string {
  return `${(bytes / (1024 * 1024)).toFixed(0)}`;
}

export function StatusBar() {
  const { data: memory } = useMemory();
  const isRecording = useIsRecording();
  const connStatus = useConnectionStatus();
  const jobs = useJobs();
  const inFlightJobs = jobs.filter(isInFlight);
  const showQueryDevtools = usePanelStore((s) => s.showQueryDevtools);
  const toggleQueryDevtools = usePanelStore((s) => s.toggleQueryDevtools);

  return (
    <div className="relative flex h-7 items-center justify-between border-t border-border bg-background px-3 text-xs">
      {/* Left: connection status + memory + REC + in-flight jobs */}
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1 text-muted-foreground">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${statusDotClass[connStatus]}`} />
          <span>{statusLabel[connStatus]}</span>
        </span>
        {memory && memory.used_bytes > 0 && (
          <span className="flex items-center gap-1 tabular-nums text-muted-foreground">
            <MemoryStick size={12} />
            {formatMB(memory.used_bytes)}MB
            {memory.limit_bytes ? ` / ${formatMB(memory.limit_bytes)}MB` : ""}
          </span>
        )}
        {isRecording && (
          <Badge variant="destructive" className="h-4 px-1.5 text-[10px]">
            <span className="mr-0.5 inline-block h-1 w-1 rounded-full bg-current animate-[pulse-dot_1s_infinite]" />
            REC
          </Badge>
        )}
        {inFlightJobs.map((job) => (
          <JobPill key={job.job_id} job={job} />
        ))}
      </div>

      {/* Right: dev-only DevTools toggle */}
      <div className="flex items-center gap-2 min-w-16 justify-end">
        {import.meta.env.DEV && (
          <button
            type="button"
            onClick={toggleQueryDevtools}
            className="rounded px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground hover:bg-muted"
            title={showQueryDevtools ? "Hide TanStack Query DevTools" : "Show TanStack Query DevTools"}
          >
            {showQueryDevtools ? "TanStackQueryDevTools ✓" : "TanStackQueryDevTools"}
          </button>
        )}
      </div>
    </div>
  );
}
