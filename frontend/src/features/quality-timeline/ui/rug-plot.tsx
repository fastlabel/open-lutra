/** Rug Plot: draws individual messages as vertical lines at high zoom levels.
 *
 * Spaces without lines represent gaps directly, so position and length are clearly visible.
 * Gap regions are highlighted with a red background + label (duration + missed count).
 */

import { Loader2 } from "lucide-react";
import { useMemo, useRef } from "react";
import { formatDuration } from "@/lib/format";
import { useQualityTimelineStore } from "../store";
import { useTimelineMessages } from "../use-timeline";

/** Time format with millisecond precision. ms display is useful for rug plot's narrow ranges. */
function formatDurationMs(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m > 0) return `${m}:${s.toFixed(2).padStart(5, "0")}`;
  return `${s.toFixed(2)}s`;
}

/** Computes a tick interval appropriate for the view range and returns an array of tick positions. */
function generateTimeTicks(from: number, to: number): number[] {
  const duration = to - from;
  if (duration <= 0) return [];

  // Target around 5-10 ticks
  const niceIntervals = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5];
  let interval = niceIntervals[0];
  for (const iv of niceIntervals) {
    if (duration / iv <= 10) {
      interval = iv;
      break;
    }
    interval = iv;
  }

  const ticks: number[] = [];
  const start = Math.ceil(from / interval) * interval;
  for (let t = start; t <= to; t += interval) {
    ticks.push(t);
  }
  return ticks;
}

/** Gap detection: detects intervals over 1.5x the expected interval as losses (catches single-frame drops) */
type RugGap = {
  startSec: number;
  endSec: number;
  durationSec: number;
  lostCount: number;
  severity: "minor" | "major";
};

function detectGaps(messages: { timestamp_sec: number }[], expectedHz: number): RugGap[] {
  if (messages.length < 2 || expectedHz <= 0) return [];
  const expectedInterval = 1 / expectedHz;
  const threshold = expectedInterval * 1.5;
  const gaps: RugGap[] = [];

  for (let i = 0; i < messages.length - 1; i++) {
    const interval = messages[i + 1].timestamp_sec - messages[i].timestamp_sec;
    if (interval > threshold) {
      const lost = Math.max(0, Math.round(interval / expectedInterval) - 1);
      if (lost > 0) {
        gaps.push({
          startSec: messages[i].timestamp_sec,
          endSec: messages[i + 1].timestamp_sec,
          durationSec: interval,
          lostCount: lost,
          severity: lost >= 3 ? "major" : "minor",
        });
      }
    }
  }
  return gaps;
}

export function RugPlot({ selectedFolder }: { selectedFolder: string }) {
  const selectedTopic = useQualityTimelineStore((s) => s.selectedTopic);
  const viewRange = useQualityTimelineStore((s) => s.viewRange);
  const playheadSec = useQualityTimelineStore((s) => s.playheadSec);

  const { data, isLoading } = useTimelineMessages(selectedFolder, selectedTopic, viewRange.from, viewRange.to);

  // While dragging, optimistically display by clipping the previous data to viewRange
  const lastDataRef = useRef(data);
  if (data) lastDataRef.current = data;
  const displayData = data ?? lastDataRef.current;

  const viewDuration = viewRange.to - viewRange.from;

  const visibleMessages = useMemo(() => {
    if (!displayData?.messages) return [];
    return displayData.messages.filter((m) => m.timestamp_sec >= viewRange.from && m.timestamp_sec <= viewRange.to);
  }, [displayData, viewRange]);

  const gaps = useMemo(() => {
    if (!visibleMessages.length || !displayData?.expected_hz) return [];
    return detectGaps(visibleMessages, displayData.expected_hz);
  }, [visibleMessages, displayData?.expected_hz]);

  if (viewDuration > 10) {
    return (
      <div className="rounded-md border border-border/50 bg-muted/5 px-3 py-3 text-center text-xs text-muted-foreground">
        Zoom in on the minimap (≤10s) to display message ticks
      </div>
    );
  }

  if (isLoading && !displayData) {
    return (
      <div className="flex items-center justify-center py-4">
        <Loader2 size={14} className="animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!visibleMessages.length && !isLoading) {
    return (
      <div className="rounded-md border border-border/50 bg-muted/5 px-3 py-3 text-center text-xs text-muted-foreground">
        No messages in this range
      </div>
    );
  }

  const ticks = generateTimeTicks(viewRange.from, viewRange.to);

  return (
    <div className="space-y-1">
      {/* Tick display area */}
      <div className="relative h-12 rounded-md border border-border bg-muted/10 overflow-hidden">
        {/* Message ticks (vertical lines) */}
        {visibleMessages.map((msg) => {
          const pct = viewDuration > 0 ? ((msg.timestamp_sec - viewRange.from) / viewDuration) * 100 : 0;
          return (
            <div key={msg.index} className="absolute top-0 h-full w-px bg-emerald-400/70" style={{ left: `${pct}%` }} />
          );
        })}

        {/* Gap regions (color-coded by severity) */}
        {gaps.map((gap) => {
          const leftPct = viewDuration > 0 ? ((gap.startSec - viewRange.from) / viewDuration) * 100 : 0;
          const widthPct = viewDuration > 0 ? (gap.durationSec / viewDuration) * 100 : 0;
          const isMajor = gap.severity === "major";
          const bgClass = isMajor
            ? "bg-red-500/20 border-x border-red-500/40"
            : "bg-amber-400/20 border-x border-amber-400/40";
          const textClass = isMajor ? "text-red-400" : "text-amber-400";
          return (
            <div
              key={gap.startSec}
              className={`absolute top-0 h-full ${bgClass}`}
              style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 0.5)}%` }}
            >
              <span className={`absolute top-0.5 left-1 text-[9px] ${textClass} whitespace-nowrap`}>
                {gap.durationSec.toFixed(3)}s / ~{gap.lostCount}
              </span>
            </div>
          );
        })}

        {/* Time-axis grid lines (faint guides) */}
        {ticks.map((t) => (
          <div
            key={t}
            className="absolute top-0 h-full w-px bg-muted-foreground/10"
            style={{ left: `${((t - viewRange.from) / viewDuration) * 100}%` }}
          />
        ))}

        {/* playhead */}
        {playheadSec >= viewRange.from && playheadSec <= viewRange.to && (
          <div
            className="absolute top-0 h-full w-0.5 bg-foreground"
            style={{ left: `${((playheadSec - viewRange.from) / viewDuration) * 100}%` }}
          />
        )}
      </div>

      {/* Time-axis labels */}
      <div className="relative h-3.5">
        {ticks.map((t) => (
          <span
            key={t}
            className="absolute text-[9px] tabular-nums text-muted-foreground -translate-x-1/2"
            style={{ left: `${((t - viewRange.from) / viewDuration) * 100}%` }}
          >
            {formatDurationMs(t)}
          </span>
        ))}
      </div>

      {/* Statistics */}
      <div className="flex gap-4 text-[10px] text-muted-foreground tabular-nums">
        <span>{visibleMessages.length} msgs</span>
        <span>{displayData?.expected_hz ?? 0}Hz</span>
        <span>
          {formatDuration(viewRange.from)} ~ {formatDuration(viewRange.to)}
        </span>
        {gaps.length > 0 && (
          <span className={gaps.some((g) => g.severity === "major") ? "text-red-400" : "text-amber-400"}>
            {gaps.length} gaps
          </span>
        )}
      </div>

      {/* Message details around gaps */}
      {gaps.length > 0 && (
        <div className="space-y-1 text-[10px] text-muted-foreground font-mono">
          {gaps.map((gap) => {
            const isMajor = gap.severity === "major";
            const bgClass = isMajor ? "bg-red-500/5" : "bg-amber-400/5";
            const textClass = isMajor ? "text-red-400" : "text-amber-400";
            return (
              <div key={gap.startSec} className={`rounded ${bgClass} px-2 py-1`}>
                <span className={textClass}>gap {gap.durationSec.toFixed(3)}s</span>
                <span className="text-muted-foreground"> ({gap.lostCount} msgs) </span>
                <span>
                  {formatDuration(gap.startSec)} → {formatDuration(gap.endSec)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
