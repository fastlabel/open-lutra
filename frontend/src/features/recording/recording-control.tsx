/** Recording action bar: record button, delay/REC indicator, robot info, command copy, and task name editor. */

import { AlertTriangle, Bot, ChevronDown, ClipboardCopy } from "lucide-react";
import { useState } from "react";
import { TaskNameInlineEditor } from "@/features/settings";
import { useConfig, useIsRecording } from "@/hooks/use-api";
import { useTopicStats } from "@/hooks/use-topics-stream";
import { isDevMode } from "@/lib/dev-mode";
import { RecordButton } from "./record-button";
import { DELAY_OPTIONS, useRecordingStore } from "./store";
import { Timer } from "./timer";

const MAX_LISTED_MISSING_TOPICS = 3;

export function RecordingControl() {
  const { data: config } = useConfig();
  const isRecording = useIsRecording();
  const topicStats = useTopicStats();

  const isCountingDown = useRecordingStore((s) => s.countdownSec !== null);
  const loading = useRecordingStore((s) => s.isStarting || s.isStopping);
  const delaySec = useRecordingStore((s) => s.delaySec);
  const setDelay = useRecordingStore((s) => s.setDelay);
  const [copied, setCopied] = useState(false);

  const buttonActive = isRecording || isCountingDown;

  // YAML default_topics that have not yet appeared in the SSE topic_stats stream.
  // Surfaced as a warning before recording starts so the user notices missing publishers.
  const missingDefaults = (config?.default_topics ?? []).filter((name) => !topicStats.some((t) => t.name === name));

  return (
    <div className="flex items-center justify-between border-b border-border bg-background px-4 py-3">
      {/* Left: record button + DELAY/REC + robot info (aligned under the bar) */}
      <div className="flex items-center gap-5">
        <RecordButton />

        {/* DELAY (idle) / REC (recording) / COUNTDOWN (counting down) */}
        <div className="flex min-w-[90px] flex-col justify-center gap-1">
          {isRecording ? (
            <>
              <span className="flex items-center gap-1.5 text-[13px] font-semibold tracking-wider text-red-400">
                <span className="h-2 w-2 rounded-full bg-current animate-[pulse-dot_1s_infinite]" />
                REC
              </span>
              <Timer className="text-[18px] font-bold text-foreground" />
            </>
          ) : isCountingDown ? (
            <>
              <span className="flex items-center gap-1.5 text-[13px] font-semibold tracking-wider text-amber-400">
                <span className="h-2 w-2 rounded-full bg-current animate-[pulse-dot_1s_infinite]" />
                COUNTDOWN
              </span>
              <Timer className="text-[18px] font-bold text-foreground" />
            </>
          ) : (
            <>
              <span className="text-[13px] tracking-wider text-muted-foreground">DELAY</span>
              <div className="relative">
                <select
                  value={delaySec}
                  onChange={(e) => setDelay(Number(e.target.value))}
                  className="w-full appearance-none rounded-md border border-border bg-muted/50 pl-2 pr-6 py-0.5 text-[13px] text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
                >
                  {DELAY_OPTIONS.map((v) => (
                    <option key={v} value={v}>
                      {v}s
                    </option>
                  ))}
                </select>
                <ChevronDown
                  size={13}
                  className="pointer-events-none absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground"
                />
              </div>
            </>
          )}
        </div>

        {/* Divider */}
        <div className="h-12 w-px bg-border/80" />

        {/* Recording target (robot name + ROS Domain ID) */}
        <div className="flex min-w-[180px] flex-col justify-center gap-1">
          <div className="flex items-center gap-1.5">
            <Bot size={14} className="text-foreground" />
            <span className="text-[13px] font-medium text-foreground">{config?.robot_name ?? "---"}</span>
          </div>
          <span className="text-[13px] text-muted-foreground">ID:{config?.ros_domain_id ?? "-"}</span>
        </div>

        {/* Command copy (dev mode only; hidden during recording or countdown) */}
        {isDevMode() && !buttonActive && (
          <button
            type="button"
            onClick={async () => {
              const command = `ros2 bag record --start-paused -s mcap ${(config?.default_topics ?? []).join(" ")}`;
              await navigator.clipboard.writeText(command);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
            disabled={loading}
            className="flex items-center gap-1.5 text-[13px] text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ClipboardCopy size={13} />
            <span>{copied ? "Copied" : "Copy command"}</span>
          </button>
        )}

        {/* Warn when YAML default topics have not yet been received via SSE.
            Hidden during recording / countdown so the bar stays focused on the active session. */}
        {!buttonActive && missingDefaults.length > 0 && (
          <span
            className="flex items-center gap-1.5 text-[13px] text-amber-400"
            role="status"
            title={missingDefaults.join("\n")}
          >
            <AlertTriangle size={13} />
            <span>
              Waiting for {missingDefaults.length} topics:{" "}
              {missingDefaults.slice(0, MAX_LISTED_MISSING_TOPICS).join(", ")}
              {missingDefaults.length > MAX_LISTED_MISSING_TOPICS && ", ...more"}
            </span>
          </span>
        )}
      </div>

      {/* Right: task name */}
      <TaskNameInlineEditor />
    </div>
  );
}
