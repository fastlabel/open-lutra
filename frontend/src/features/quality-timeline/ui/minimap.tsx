/** Minimap: heatmap of the entire recording + a draggable range selector.
 *
 * Inspired by TradingView-style range selectors:
 * - Background shows an aggregated gap-density heatmap of all topics
 * - View range is shown as a semi-transparent rectangle with handles on each end
 * - Drag the middle to slide, drag the handles to resize
 * - Time-axis labels are always displayed
 * - The selected range label is shown
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { TimelineData } from "@/api/generated/schemas";
import { formatDuration } from "@/lib/format";
import { useQualityTimelineStore } from "../store";

/** Minimum view range (seconds) */
const MIN_RANGE_SEC = 0.5;

/** Drag state type */
type DragMode = "move" | "resize-left" | "resize-right" | null;

/** Background heatmap: shows the selected topic's gaps, or the aggregated all-topic view when none is selected. */
function MinimapBackground({ data, selectedTopic }: { data: TimelineData; selectedTopic: string | null }) {
  if (!data.topics.length || !data.topics[0].bins.length) return null;

  const targets = selectedTopic ? data.topics.filter((t) => t.name === selectedTopic) : data.topics;
  if (!targets.length) return null;

  const totalBins = targets[0].bins.length;

  // Aggregate the maximum severity for each bin: "major" > "minor" > "ok"
  const binSeverities: ("ok" | "minor" | "major")[] = [];
  for (let i = 0; i < totalBins; i++) {
    let sev: "ok" | "minor" | "major" = "ok";
    for (const topic of targets) {
      const bin = topic.bins[i];
      if (bin?.has_gap) {
        sev = "major";
        break;
      }
      if (bin?.has_minor_loss) sev = "minor";
    }
    binSeverities.push(sev);
  }

  const gradientStops = binSeverities
    .map((sev, i) => {
      const hue = sev === "major" ? 0 : sev === "minor" ? 45 : 152;
      const alpha = sev === "ok" ? 0.15 : 0.4;
      const pct = (i / totalBins) * 100;
      const pctEnd = ((i + 1) / totalBins) * 100;
      const color = `hsla(${hue}, 50%, 50%, ${alpha})`;
      return `${color} ${pct}%, ${color} ${pctEnd}%`;
    })
    .join(", ");

  return <div className="absolute inset-0" style={{ background: `linear-gradient(to right, ${gradientStops})` }} />;
}

/** Generates ticks (grid marks) for the time axis. */
function generateTicks(durationSec: number, widthPx: number): number[] {
  if (durationSec <= 0 || widthPx <= 0) return [];

  // Reserve at least 60px per tick
  const maxTicks = Math.floor(widthPx / 60);
  const niceIntervals = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  let interval = niceIntervals[0];
  for (const iv of niceIntervals) {
    if (durationSec / iv <= maxTicks) {
      interval = iv;
      break;
    }
    interval = iv;
  }

  const ticks: number[] = [];
  for (let t = 0; t <= durationSec; t += interval) {
    ticks.push(t);
  }
  return ticks;
}

export function Minimap({ data }: { data: TimelineData | null }) {
  const durationSec = useQualityTimelineStore((s) => s.durationSec);
  const viewRange = useQualityTimelineStore((s) => s.viewRange);
  const playheadSec = useQualityTimelineStore((s) => s.playheadSec);
  const setViewRange = useQualityTimelineStore((s) => s.setViewRange);
  const setIsDragging = useQualityTimelineStore((s) => s.setIsDragging);
  const selectedTopic = useQualityTimelineStore((s) => s.selectedTopic);

  const containerRef = useRef<HTMLDivElement>(null);
  const [dragMode, setDragMode] = useState<DragMode>(null);
  const dragStartRef = useRef({ x: 0, from: 0, to: 0 });
  const wasDraggingRef = useRef(false);

  const pxToSec = useCallback(
    (px: number) => {
      const el = containerRef.current;
      if (!el || durationSec <= 0) return 0;
      return (px / el.clientWidth) * durationSec;
    },
    [durationSec],
  );

  const leftPct = durationSec > 0 ? (viewRange.from / durationSec) * 100 : 0;
  const widthPct = durationSec > 0 ? ((viewRange.to - viewRange.from) / durationSec) * 100 : 100;
  const playheadPct = durationSec > 0 ? (playheadSec / durationSec) * 100 : 0;

  const handleMouseDown = useCallback(
    (e: React.MouseEvent, mode: DragMode) => {
      e.preventDefault();
      e.stopPropagation();
      setDragMode(mode);
      setIsDragging(true);
      wasDraggingRef.current = true;
      dragStartRef.current = { x: e.clientX, from: viewRange.from, to: viewRange.to };
    },
    [viewRange, setIsDragging],
  );

  useEffect(() => {
    if (!dragMode) return;

    const calcRange = (deltaSec: number) => {
      const { from: sf, to: st } = dragStartRef.current;
      if (dragMode === "resize-left") return { from: Math.max(0, Math.min(st - MIN_RANGE_SEC, sf + deltaSec)), to: st };
      if (dragMode === "resize-right")
        return { from: sf, to: Math.min(durationSec, Math.max(sf + MIN_RANGE_SEC, st + deltaSec)) };
      const span = st - sf;
      const clamped = Math.max(0, Math.min(durationSec - span, sf + deltaSec));
      return { from: clamped, to: clamped + span };
    };

    const handleMouseMove = (e: MouseEvent) => {
      setViewRange(calcRange(pxToSec(e.clientX - dragStartRef.current.x)));
    };
    const handleMouseUp = () => {
      setDragMode(null);
      setIsDragging(false);
      // Prevent the post-mouseup click event from misfiring the background click
      setTimeout(() => {
        wasDraggingRef.current = false;
      }, 0);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [dragMode, durationSec, pxToSec, setViewRange, setIsDragging]);

  // Click minimap background → jump to that position (ignored right after dragging)
  const handleBackgroundClick = useCallback(
    (e: React.MouseEvent) => {
      if (wasDraggingRef.current) return;
      const el = containerRef.current;
      if (!el || durationSec <= 0) return;

      const rect = el.getBoundingClientRect();
      const clickSec = ((e.clientX - rect.left) / rect.width) * durationSec;
      const halfSpan = (viewRange.to - viewRange.from) / 2;
      const newFrom = Math.max(0, Math.min(durationSec - halfSpan * 2, clickSec - halfSpan));
      setViewRange({ from: newFrom, to: newFrom + halfSpan * 2 });
    },
    [durationSec, viewRange, setViewRange],
  );

  if (durationSec <= 0) return null;

  const ticks = generateTicks(durationSec, containerRef.current?.clientWidth ?? 400);

  return (
    <div className="space-y-0.5">
      {/* Time-axis labels */}
      <div className="relative h-4" ref={containerRef}>
        {ticks.map((t) => (
          <span
            key={t}
            className="absolute text-[9px] tabular-nums text-muted-foreground -translate-x-1/2"
            style={{ left: `${(t / durationSec) * 100}%` }}
          >
            {formatDuration(t)}
          </span>
        ))}
      </div>

      {/* Minimap body */}
      <div
        className="relative h-10 rounded border border-border/50 overflow-hidden cursor-pointer select-none"
        onClick={handleBackgroundClick}
      >
        {/* Background heatmap */}
        {data && <MinimapBackground data={data} selectedTopic={selectedTopic} />}

        {/* Overlays outside the selected range (darkened) */}
        <div className="absolute inset-y-0 left-0 bg-black/40" style={{ width: `${leftPct}%` }} />
        <div className="absolute inset-y-0 right-0 bg-black/40" style={{ width: `${100 - leftPct - widthPct}%` }} />

        {/* Selected range */}
        <div
          className={`absolute inset-y-0 border-x-2 border-ring/70 ${dragMode === "move" ? "cursor-grabbing" : "cursor-grab"}`}
          style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 0.5)}%` }}
          onMouseDown={(e) => handleMouseDown(e, "move")}
        >
          {/* Selected range label */}
          <div className="absolute inset-x-0 top-0.5 flex justify-center pointer-events-none">
            <span className="rounded bg-background/80 px-1 text-[9px] tabular-nums text-muted-foreground whitespace-nowrap">
              {formatDuration(viewRange.from)} ~ {formatDuration(viewRange.to)}
            </span>
          </div>
        </div>

        {/* Left handle */}
        <div
          className="absolute inset-y-0 w-3 cursor-col-resize z-10 group"
          style={{ left: `calc(${leftPct}% - 6px)` }}
          onMouseDown={(e) => handleMouseDown(e, "resize-left")}
        >
          <div className="absolute inset-y-1 left-1 w-1 rounded-full bg-ring/80 group-hover:bg-ring" />
        </div>

        {/* Right handle */}
        <div
          className="absolute inset-y-0 w-3 cursor-col-resize z-10 group"
          style={{ left: `calc(${leftPct + widthPct}% - 6px)` }}
          onMouseDown={(e) => handleMouseDown(e, "resize-right")}
        >
          <div className="absolute inset-y-1 right-1 w-1 rounded-full bg-ring/80 group-hover:bg-ring" />
        </div>

        {/* Playhead */}
        <div
          className="absolute inset-y-0 w-px bg-foreground/80 pointer-events-none z-20"
          style={{ left: `${playheadPct}%` }}
        />
      </div>
    </div>
  );
}
