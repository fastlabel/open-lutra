/** Joint Position Graph: renders JointState position time series with uPlot.
 *
 * The X axis is synchronized with the Timeline Controller's viewRange, and the playhead position is drawn as a vertical line.
 */

import { Activity, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import uPlot from "uplot";
import { useGetJoints } from "@/api/generated/media/media";
import type { JointTopicsResponse } from "@/api/generated/schemas";
import { getChartAxisColors } from "@/lib/chart-theme";
import { formatElapsed } from "@/lib/format";
import { useQualityTimelineStore } from "../store";

// rgba with alpha 0.7 so the dense 7-axis overlay reads as subdued background detail rather than dominating the chart.
const COLORS = [
  "rgba(34, 197, 94, 0.7)",
  "rgba(59, 130, 246, 0.7)",
  "rgba(245, 158, 11, 0.7)",
  "rgba(239, 68, 68, 0.7)",
  "rgba(168, 85, 247, 0.7)",
  "rgba(6, 182, 212, 0.7)",
  "rgba(249, 115, 22, 0.7)",
  "rgba(236, 72, 153, 0.7)",
];

/** uPlot plugin that draws the playhead vertical line. */
function playheadPlugin(playheadRef: React.RefObject<number>): uPlot.Plugin {
  return {
    hooks: {
      draw: [
        (u: uPlot) => {
          const sec = playheadRef.current;
          if (sec == null || sec <= 0) return;
          const x = u.valToPos(sec, "x", true);
          const { left, top, width, height } = u.bbox;
          if (x < left || x > left + width) return;

          u.ctx.save();
          u.ctx.beginPath();
          u.ctx.strokeStyle = "#e5e5e5";
          u.ctx.lineWidth = 1;
          u.ctx.setLineDash([]);
          u.ctx.moveTo(x, top);
          u.ctx.lineTo(x, top + height);
          u.ctx.stroke();
          u.ctx.restore();
        },
      ],
    },
  };
}

/** Builds tooltip HTML from the cursor position. */
function buildTooltipHtml(u: uPlot, idx: number): string | null {
  const xVal = u.data[0]?.[idx];
  if (xVal == null) return null;

  const lines: string[] = [`<div class="mb-1 text-muted-foreground">${formatElapsed(xVal)}</div>`];
  for (let i = 1; i < u.series.length; i++) {
    const series = u.series[i];
    const v = u.data[i]?.[idx];
    if (v == null) continue;
    const color = typeof series.stroke === "string" ? series.stroke : "#888";
    lines.push(
      `<div class="flex items-center gap-1.5">
        <span class="inline-block h-2 w-2 rounded-full" style="background:${color}"></span>
        <span class="text-foreground/80">${series.label ?? ""}</span>
        <span class="ml-auto tabular-nums text-foreground">${v.toFixed(3)}</span>
      </div>`,
    );
  }
  return lines.join("");
}

/** Places the tooltip element to the right of the cursor (or to the left if it would overflow). */
function positionTooltip(tooltipEl: HTMLDivElement, u: uPlot, left: number, top: number): void {
  const tooltipWidth = tooltipEl.offsetWidth;
  const overWidth = u.over.clientWidth;
  const xPos = left + tooltipWidth + 12 > overWidth ? left - tooltipWidth - 8 : left + 12;
  tooltipEl.style.left = `${Math.max(0, xPos)}px`;
  tooltipEl.style.top = `${Math.max(0, top - 8)}px`;
}

/** Custom tooltip plugin showing joint name + value on hover.
 *
 * uPlot's default legend is fixed beneath the chart, which breaks the layout for
 * multi-joint cases (e.g., 7 axes) as it grows vertically. We use a floating div
 * to show a tooltip near the hover position instead.
 */
function tooltipPlugin(): uPlot.Plugin {
  let tooltipEl: HTMLDivElement | null = null;

  return {
    hooks: {
      init: [
        (u: uPlot) => {
          tooltipEl = document.createElement("div");
          tooltipEl.className =
            "pointer-events-none absolute z-10 hidden rounded-md border border-border bg-background/95 px-2 py-1.5 text-[11px] font-mono shadow-lg backdrop-blur-sm";
          u.over.appendChild(tooltipEl);
        },
      ],
      setCursor: [
        (u: uPlot) => {
          if (!tooltipEl) return;
          const { left, top, idx } = u.cursor;
          if (idx == null || left == null || top == null || left < 0 || top < 0) {
            tooltipEl.style.display = "none";
            return;
          }
          const html = buildTooltipHtml(u, idx);
          if (html == null) {
            tooltipEl.style.display = "none";
            return;
          }
          tooltipEl.innerHTML = html;
          tooltipEl.style.display = "block";
          positionTooltip(tooltipEl, u, left, top);
        },
      ],
      destroy: [
        () => {
          tooltipEl?.remove();
          tooltipEl = null;
        },
      ],
    },
  };
}

/** Builds uPlot series data and options. */
function buildJointSeries(topic: JointTopicsResponse["topics"][number]) {
  const xs = new Float64Array(topic.timestamps);
  const seriesData: (Float64Array | number[])[] = [xs];
  const jointCount = topic.joint_names.length || (topic.positions[0]?.length ?? 0);
  const seriesOpts: uPlot.Series[] = [{ label: "Time", value: (_u, v) => (v != null ? formatElapsed(v) : "--") }];

  for (let j = 0; j < jointCount; j++) {
    const ys = new Float64Array(topic.timestamps.length);
    for (let i = 0; i < topic.timestamps.length; i++) {
      ys[i] = topic.positions[i]?.[j] ?? 0;
    }
    seriesData.push(ys);
    seriesOpts.push({
      label: topic.joint_names[j] ?? `joint_${j}`,
      stroke: COLORS[j % COLORS.length],
      width: 0.75,
      value: (_u: uPlot, v: number | null) => (v != null ? v.toFixed(3) : "--"),
    });
  }
  return { seriesData: seriesData as uPlot.AlignedData, seriesOpts };
}

function JointChart({ topic }: { topic: JointTopicsResponse["topics"][number] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const uplotRef = useRef<uPlot | null>(null);
  const viewRange = useQualityTimelineStore((s) => s.viewRange);
  const playheadSec = useQualityTimelineStore((s) => s.playheadSec);
  const playheadRef = useRef(playheadSec);
  playheadRef.current = playheadSec;

  useEffect(() => {
    if (!containerRef.current || !topic.timestamps.length) return;

    if (uplotRef.current) {
      uplotRef.current.destroy();
      uplotRef.current = null;
    }

    const el = containerRef.current;
    const { seriesData, seriesOpts } = buildJointSeries(topic);

    const { axis: axisColor, grid: gridColor } = getChartAxisColors();
    const opts: uPlot.Options = {
      width: el.clientWidth || 600,
      height: el.clientHeight || 160,
      series: seriesOpts,
      plugins: [playheadPlugin(playheadRef), tooltipPlugin()],
      scales: { x: { time: false } },
      axes: [
        {
          stroke: axisColor,
          grid: { stroke: gridColor, width: 1 },
          values: (_u, vals) => vals.map((v) => formatElapsed(v)),
          font: "11px monospace",
        },
        {
          stroke: axisColor,
          grid: { stroke: gridColor, width: 1 },
          label: "rad",
          labelFont: "11px monospace",
          font: "11px monospace",
          size: 55,
        },
      ],
      cursor: { drag: { x: false, y: false } },
      // Hide the legend since the hover tooltip replaces it (many joints would break the layout)
      legend: { show: false },
    };

    uplotRef.current = new uPlot(opts, seriesData, el);
    return () => {
      uplotRef.current?.destroy();
      uplotRef.current = null;
    };
  }, [topic]);

  // viewRange + playhead → bundle X-axis scale update and plugin redraw into one effect
  // biome-ignore lint/correctness/useExhaustiveDependencies: plugin redraw must be triggered by playheadSec
  useEffect(() => {
    const u = uplotRef.current;
    if (!u) return;
    const { min, max } = u.scales.x;
    if (min !== viewRange.from || max !== viewRange.to) {
      u.setScale("x", { min: viewRange.from, max: viewRange.to });
    } else {
      u.redraw(false);
    }
  }, [viewRange, playheadSec]);

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (uplotRef.current) {
          const { width, height } = entry.contentRect;
          if (width > 0 && height > 0) uplotRef.current.setSize({ width, height });
        }
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const shortName = topic.topic.split("/").filter(Boolean).slice(0, 2).join("/");

  return (
    <div>
      <span className="text-[10px] text-muted-foreground">{shortName}</span>
      <div ref={containerRef} className="h-40 w-full" />
    </div>
  );
}

export function JointGraph({ selectedFolder, enabled = true }: { selectedFolder: string; enabled?: boolean }) {
  const { data, isLoading } = useGetJoints<JointTopicsResponse>(
    { path: selectedFolder, decimation: 20 },
    {
      query: {
        enabled: !!selectedFolder && enabled,
        staleTime: 60_000,
        select: (resp) => resp.data as JointTopicsResponse,
      },
    },
  );

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-4 justify-center text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" />
        <span>Loading Joint data...</span>
      </div>
    );
  }

  if (!data?.topics?.length) {
    return (
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Activity size={14} className="text-muted-foreground" />
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Joint Positions</span>
        </div>
        <p className="text-xs text-muted-foreground">No JointState topic found</p>
      </div>
    );
  }

  const gridCols = data.topics.length === 1 ? "grid-cols-1" : "grid-cols-1 lg:grid-cols-2";

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Activity size={14} className="text-muted-foreground" />
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Joint Positions</span>
      </div>

      <div className={`grid gap-3 ${gridCols}`}>
        {data.topics.map((topic) => (
          <JointChart key={topic.topic} topic={topic} />
        ))}
      </div>
    </div>
  );
}
