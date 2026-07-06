/** Loss Rate static chart: renders the count-based loss rate from MCAP timeline data.
 *
 * Same UI as the recording page's real-time version (uPlot, inverted Y axis),
 * but the data source is the timeline API instead of SSE, and the full dataset is rendered at once.
 * The per-point series is a sliding-window "1 − received / expected" — see `loss-rate-utils.ts`.
 */

import { useEffect, useRef } from "react";
import uPlot from "uplot";
import type { TimelineData } from "@/api/generated/schemas";
import { getChartAxisColors } from "@/lib/chart-theme";
import { formatElapsed } from "@/lib/format";
import { buildLossRateData } from "../loss-rate-utils";
import { useQualityTimelineStore } from "../store";

const COLORS = [
  "#22c55e",
  "#3b82f6",
  "#f59e0b",
  "#ef4444",
  "#a855f7",
  "#06b6d4",
  "#f97316",
  "#ec4899",
  "#14b8a6",
  "#84cc16",
];
const WARN_THRESHOLD = 2;
const DANGER_THRESHOLD = 5;

/** uPlot plugin that draws threshold lines. */
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

export function LossRateChart({ data }: { data: TimelineData }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const uplotRef = useRef<uPlot | null>(null);
  const selectedTopic = useQualityTimelineStore((s) => s.selectedTopic);
  const viewRange = useQualityTimelineStore((s) => s.viewRange);
  const playheadSec = useQualityTimelineStore((s) => s.playheadSec);

  const playheadRef = useRef(playheadSec);
  playheadRef.current = playheadSec;

  const filtered = selectedTopic ? data.topics.filter((t) => t.name === selectedTopic) : data.topics;
  const topicKey = filtered.map((t) => t.name).join(",");

  // Create/recreate the uPlot instance (only when topicKey changes)
  useEffect(() => {
    const topicNames = topicKey.split(",").filter(Boolean);
    if (!containerRef.current || topicNames.length === 0) return;

    if (uplotRef.current) {
      uplotRef.current.destroy();
      uplotRef.current = null;
    }

    const el = containerRef.current;
    const width = el.clientWidth || 600;
    const height = el.clientHeight || 180;

    const series: uPlot.Series[] = [
      { label: "Time", value: (_u, v) => (v != null ? formatElapsed(v) : "--") },
      ...topicNames.map((name, i) => {
        const color = COLORS[i % COLORS.length];
        return {
          label: name.split("/").filter(Boolean).slice(0, 2).join("/"),
          stroke: color,
          width: 1.5,
          // Default uPlot points are hollow circles filled with the chart background (white),
          // which read as noisy dots in dense regions. Use the line color so dots blend in.
          points: { show: true, size: 4, fill: color, stroke: color },
          value: (_u: uPlot, v: number | null) => (v != null ? `${v.toFixed(1)}%` : "--"),
        };
      }),
    ];

    const { axis: axisColor, grid: gridColor } = getChartAxisColors();
    const opts: uPlot.Options = {
      width,
      height,
      series,
      plugins: [thresholdPlugin(), playheadPlugin(playheadRef)],
      scales: {
        x: { time: false },
        // Keep a [0, 10]% window for the common near-zero case, but expand to fit
        // when a topic runs steadily below its expected rate (count-based loss can
        // reach tens of %), so a sustained deficit stays on-screen instead of
        // clipping off the top.
        y: { dir: -1 as const, range: (_u, _min, max) => [0, Math.max(10, max ?? 10)] },
      },
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
          font: "11px monospace",
          // Omit the label ("loss%") to save left margin — values already include "%"
          size: 36,
          values: (_u, vals) => vals.map((v) => `${v}%`),
        },
      ],
      cursor: { drag: { x: false, y: false } },
      legend: { show: false },
    };

    const chartData = buildLossRateData(data.topics, selectedTopic, data.duration_sec, data.bin_width_sec);
    uplotRef.current = new uPlot(opts, chartData, el);

    return () => {
      uplotRef.current?.destroy();
      uplotRef.current = null;
    };
  }, [data, topicKey, selectedTopic]);

  // selectedTopic change → re-set data
  useEffect(() => {
    if (!uplotRef.current) return;
    uplotRef.current.setData(buildLossRateData(data.topics, selectedTopic, data.duration_sec, data.bin_width_sec));
  }, [selectedTopic, data]);

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

  // Resize handling
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

  return <div ref={containerRef} className="h-44 w-full" />;
}
