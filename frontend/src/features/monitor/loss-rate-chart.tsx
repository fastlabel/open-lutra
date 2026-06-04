/** Loss Rate real-time chart: draws the per-topic loss-rate trend.
 *
 * The Y axis is inverted (0% on top = stable, lower = worse).
 * All topics share a unified 0-10% scale so mixed-Hz topics are comparable.
 * Only topics selected as recording targets are drawn.
 */
import { useEffect, useMemo, useRef } from "react";
import uPlot from "uplot";
import { useLiveTopicsStore } from "@/features/live-topics";
import { getChartAxisColors } from "@/lib/chart-theme";
import { type QualitySnapshot, type RecordingMarker, useQualityHistoryStore } from "@/stores/quality-history-store";

// --- Per-topic color palette ---
const COLORS = [
  "#22c55e", // emerald
  "#3b82f6", // blue
  "#f59e0b", // amber
  "#ef4444", // red
  "#a855f7", // purple
  "#06b6d4", // cyan
  "#f97316", // orange
  "#ec4899", // pink
  "#14b8a6", // teal
  "#84cc16", // lime
];

/** Display window length in seconds */
const WINDOW_SEC = 30;

/** Seconds scrolled per wheel step */
const SCROLL_STEP_SEC = 3;

/** Warning threshold (%) */
const WARN_THRESHOLD = 2;

/** Danger threshold (%) */
const DANGER_THRESHOLD = 5;

/** Computes the X-axis display range from the scroll offset. */
function resolveXRange(maxElapsed: number, scrollOffset: number | null): { min: number; max: number } {
  if (scrollOffset != null) return { min: scrollOffset, max: scrollOffset + WINDOW_SEC };
  if (maxElapsed <= WINDOW_SEC) return { min: 0, max: WINDOW_SEC };
  return { min: maxElapsed - WINDOW_SEC, max: maxElapsed };
}

/** Computes the post-scroll X-axis min and the scrollOffset to persist, from a wheel delta.
 *
 * - newMin is clamped to [firstElapsed, maxElapsed - WINDOW_SEC]
 * - If newMin is close to the right edge (>= maxElapsed - WINDOW_SEC - 1), return nextOffset=null to re-enter "follow mode"
 */
function computeScrollState(
  currentMin: number,
  delta: number,
  firstElapsed: number,
  maxElapsed: number,
): { newMin: number; nextOffset: number | null } {
  const newMin = Math.max(firstElapsed, Math.min(currentMin + delta, maxElapsed - WINDOW_SEC));
  const nextOffset = newMin >= maxElapsed - WINDOW_SEC - 1 ? null : newMin;
  return { newMin, nextOffset };
}

function buildLossRateData(snapshots: QualitySnapshot[], topicNames: string[]): uPlot.AlignedData {
  const xs = new Float64Array(snapshots.length);
  for (let i = 0; i < snapshots.length; i++) {
    xs[i] = snapshots[i].elapsed;
  }

  const series: (Float64Array | number[])[] = [xs];
  for (const name of topicNames) {
    const ys = new Float64Array(snapshots.length);
    for (let i = 0; i < snapshots.length; i++) {
      ys[i] = (snapshots[i].loss[name] ?? 0) * 100; // 0-100%
    }
    series.push(ys);
  }
  return series as uPlot.AlignedData;
}

/** Formats elapsed seconds as MM:SS. */
function fmtElapsed(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Returns the color and label for a marker type. */
function markerStyle(type: string) {
  return type === "start" ? { color: "#22c55e", label: "REC" } : { color: "#ef4444", label: "STOP" };
}

/** Draws a single marker vertical line. */
function drawMarkerLine(ctx: CanvasRenderingContext2D, m: RecordingMarker, x: number, top: number, height: number) {
  const style = markerStyle(m.type);
  ctx.beginPath();
  ctx.strokeStyle = style.color;
  ctx.lineWidth = 2;
  ctx.setLineDash([4, 4]);
  ctx.moveTo(x, top);
  ctx.lineTo(x, top + height);
  ctx.stroke();

  ctx.fillStyle = style.color;
  ctx.font = "bold 12px monospace";
  ctx.textAlign = "center";
  ctx.fillText(style.label, x, top + 14);
}

/** uPlot plugin that draws recording marker vertical lines. */
function markersPlugin(markersRef: React.RefObject<RecordingMarker[]>): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const markers = markersRef.current;
          if (!markers || markers.length === 0) return;

          const { left, top, width, height } = u.bbox;
          u.ctx.save();
          for (const m of markers) {
            const x = u.valToPos(m.elapsed, "x", true);
            if (x >= left && x <= left + width) {
              drawMarkerLine(u.ctx, m, x, top, height);
            }
          }
          u.ctx.restore();
        },
      ],
    },
  };
}

/** uPlot plugin that draws warning/danger threshold lines. */
function thresholdPlugin(): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const { left, top, width, height } = u.bbox;
          u.ctx.save();

          for (const { value, color, label } of [
            { value: WARN_THRESHOLD, color: "#f59e0b", label: "warn" },
            { value: DANGER_THRESHOLD, color: "#ef4444", label: "danger" },
          ]) {
            const y = u.valToPos(value, "y", true);
            if (y >= top && y <= top + height) {
              u.ctx.beginPath();
              u.ctx.strokeStyle = color;
              u.ctx.lineWidth = 1;
              u.ctx.setLineDash([4, 4]);
              u.ctx.globalAlpha = 0.5;
              u.ctx.moveTo(left, y);
              u.ctx.lineTo(left + width, y);
              u.ctx.stroke();

              u.ctx.globalAlpha = 0.7;
              u.ctx.fillStyle = color;
              u.ctx.font = "10px monospace";
              u.ctx.textAlign = "right";
              u.ctx.fillText(label, left + width - 4, y - 3);
            }
          }

          u.ctx.restore();
        },
      ],
    },
  };
}

export function LossRateChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const uplotRef = useRef<uPlot | null>(null);
  const prevKeyRef = useRef("");
  const snapshots = useQualityHistoryStore((state) => state.snapshots);
  const allTopicNames = useQualityHistoryStore((state) => state.topicNames);
  const markers = useQualityHistoryStore((state) => state.markers);
  const markersRef = useRef(markers);
  markersRef.current = markers;
  const selectedTopics = useLiveTopicsStore((s) => s.selectedTopics);

  // Restrict the chart to topics chosen as recording targets (preserving SSE-discovery order).
  const topicNames = useMemo(() => allTopicNames.filter((n) => selectedTopics.has(n)), [allTopicNames, selectedTopics]);

  const scrollOffsetRef = useRef<number | null>(null);

  // Create/recreate the uPlot instance
  useEffect(() => {
    if (!containerRef.current || topicNames.length === 0) return;

    const key = topicNames.join(",");
    if (uplotRef.current && prevKeyRef.current === key) {
      return;
    }
    prevKeyRef.current = key;

    if (uplotRef.current) {
      uplotRef.current.destroy();
      uplotRef.current = null;
    }

    const series: uPlot.Series[] = [
      { label: "Time", value: (_u, v) => (v != null ? fmtElapsed(v) : "--") },
      ...topicNames.map((name, i) => ({
        label: name.split("/").filter(Boolean).slice(0, 2).join("/"),
        stroke: COLORS[i % COLORS.length],
        width: 1.5,
        value: (_u: uPlot, v: number | null) => (v != null ? `${v.toFixed(1)}%` : "--"),
      })),
    ];

    const { axis: axisColor, grid: gridColor } = getChartAxisColors();
    const opts: uPlot.Options = {
      width: containerRef.current.clientWidth || 600,
      height: containerRef.current.clientHeight || 200,
      series,
      plugins: [markersPlugin(markersRef), thresholdPlugin()],
      scales: {
        x: { time: false },
        y: { dir: -1 as const, range: [0, 10] }, // Inverted: 0% on top, 10% at the bottom
      },
      axes: [
        {
          stroke: axisColor,
          grid: { stroke: gridColor, width: 1 },
          values: (_u, vals) => vals.map((v) => fmtElapsed(v)),
          font: "11px monospace",
        },
        {
          stroke: axisColor,
          grid: { stroke: gridColor, width: 1 },
          label: "loss%",
          labelFont: "11px monospace",
          font: "11px monospace",
          size: 50,
          values: (_u, vals) => vals.map((v) => `${v}%`),
        },
      ],
      cursor: {
        drag: { x: false, y: false },
      },
      legend: { show: false },
    };

    uplotRef.current = new uPlot(opts, buildLossRateData(snapshots, topicNames), containerRef.current);

    return () => {
      uplotRef.current?.destroy();
      uplotRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicNames, snapshots]);

  // Data updates + 30-second window control
  useEffect(() => {
    if (!uplotRef.current || topicNames.length === 0 || snapshots.length === 0) return;

    uplotRef.current.setData(buildLossRateData(snapshots, topicNames));
    uplotRef.current.setScale("x", resolveXRange(snapshots[snapshots.length - 1].elapsed, scrollOffsetRef.current));
  }, [snapshots, topicNames]);

  // Wheel to scroll left/right
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const onWheel = (e: WheelEvent) => {
      // Prefer the horizontal component (horizontal wheel/trackpad); fall back to vertical
      const delta = ((Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY) / 100) * SCROLL_STEP_SEC;
      if (delta === 0) return;

      e.preventDefault();
      const u = uplotRef.current;
      if (!u) return;

      const snaps = useQualityHistoryStore.getState().snapshots;
      if (snaps.length === 0) return;

      const { newMin, nextOffset } = computeScrollState(
        u.scales.x.min ?? 0,
        delta,
        snaps[0].elapsed,
        snaps[snaps.length - 1].elapsed,
      );
      scrollOffsetRef.current = nextOffset;
      u.setScale("x", { min: newMin, max: newMin + WINDOW_SEC });
    };

    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Resize handling
  useEffect(() => {
    if (!containerRef.current) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (uplotRef.current) {
          const { width, height } = entry.contentRect;
          if (width > 0 && height > 0) {
            uplotRef.current.setSize({ width, height });
          }
        }
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  if (topicNames.length === 0) {
    const message =
      selectedTopics.size === 0
        ? "Select recording-target topics to see their quality here"
        : "Waiting for SSE connection... the chart will appear once topic data starts streaming";
    return <div className="flex h-full items-center justify-center text-sm text-muted-foreground">{message}</div>;
  }

  return <div ref={containerRef} className="h-full w-full" />;
}
