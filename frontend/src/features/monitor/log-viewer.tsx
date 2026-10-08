/** Log viewer: shows severity filters and the log list. */
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { useLogs } from "@/hooks/use-topics-stream";
import { type Severity, useLogStore } from "./store";

const severityStyles: Record<string, string> = {
  info: "text-blue-600 dark:text-blue-400",
  warning: "text-amber-600 dark:text-amber-400",
  danger: "text-red-600 dark:text-red-400",
};

const severityBadgeStyles: Record<Severity, { active: string; inactive: string }> = {
  info: {
    active: "bg-blue-500/20 text-blue-600 dark:text-blue-400 border-blue-500/30",
    inactive: "bg-muted text-muted-foreground border-border",
  },
  warning: {
    active: "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30",
    inactive: "bg-muted text-muted-foreground border-border",
  },
  danger: {
    active: "bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30",
    inactive: "bg-muted text-muted-foreground border-border",
  },
};

function formatTimestamp(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function LogViewer() {
  const severityFilter = useLogStore((state) => state.severityFilter);
  const toggleFilter = useLogStore((state) => state.toggleSeverityFilter);
  const scrollRef = useRef<HTMLDivElement>(null);

  const logs = useLogs();
  const filteredLogs = logs.filter((log) => severityFilter.has(log.severity as Severity));

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, []);

  return (
    <div className="flex h-full flex-col">
      {/* Filter bar */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-1">
        <span className="text-xs text-muted-foreground">{filteredLogs.length} entries</span>
        <div className="flex gap-1 ml-auto">
          {(["info", "warning", "danger"] as Severity[]).map((severity) => {
            const isActive = severityFilter.has(severity);
            const styles = severityBadgeStyles[severity];
            return (
              <Button
                key={severity}
                variant="outline"
                size="xs"
                className={`h-5 px-2 text-xs border ${isActive ? styles.active : styles.inactive}`}
                onClick={() => toggleFilter(severity)}
              >
                {severity}
              </Button>
            );
          })}
        </div>
      </div>

      {/* Log list */}
      <div className="min-h-0 flex-1 overflow-y-auto" ref={scrollRef}>
        <div className="p-1 font-mono text-sm">
          {filteredLogs.length === 0 ? (
            <p className="p-3 text-center text-muted-foreground">No log entries</p>
          ) : (
            filteredLogs.map((log) => (
              <div key={log.id} className="flex gap-2 px-2 py-0.5 hover:bg-muted/30">
                <span className="shrink-0 text-muted-foreground">{formatTimestamp(log.timestamp)}</span>
                <span className={`shrink-0 w-14 uppercase ${severityStyles[log.severity] ?? "text-muted-foreground"}`}>
                  {log.severity === "danger" ? "err" : log.severity}
                </span>
                <span className="shrink-0 w-7 text-muted-foreground">{log.source === "ui" ? "UI" : "API"}</span>
                <span className="text-foreground">{log.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
