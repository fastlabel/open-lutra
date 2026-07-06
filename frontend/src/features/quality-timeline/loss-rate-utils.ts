/** Pure helpers for Loss Rate chart series construction.
 *
 * Each sample point at x = i * STEP is the count-based loss% inside a WINDOW-wide window
 * centered on x: loss% = 1 − received / expected, aggregated from the per-bin `count` and
 * `expected` values (which already reflect the configured expected_hz). This mirrors the
 * per-topic loss_rate in the quality report, so a stream that runs steadily below its
 * configured rate shows a sustained deficit here — not just the discrete IQR dropouts.
 */

import type uPlot from "uplot";
import type { TimelineTopic } from "@/api/generated/schemas";

/** Sliding-window length in seconds. The denominator (Σ bin.expected over the window ≈
 * expected_hz × WINDOW_SEC) keeps the 2% / 5% warn/danger threshold semantics. */
export const LOSS_RATE_WINDOW_SEC = 1.0;

/** Distance between successive sample points in seconds. */
export const LOSS_RATE_STEP_SEC = 0.1;

/** Builds per-point count-based loss_rate (%) for a single topic.
 *
 * Window i is centered on x = i * STEP_SEC and spans [x - WINDOW/2, x + WINDOW/2). The loss%
 * is 1 − (received frames in the window) / (expected frames in the window), so a smooth stream
 * running below its expected rate produces a sustained plateau. Bins are contiguous starting at
 * t=0 with `binWidthSec` spacing, so window membership is derived directly from the bin index.
 */
export function buildTopicLossRateSeries(topic: TimelineTopic, numPoints: number, binWidthSec: number): Float64Array {
  const ys = new Float64Array(numPoints);
  const bins = topic.bins;
  if (topic.expected_hz <= 0 || bins.length === 0 || binWidthSec <= 0) return ys;

  // Prefix sums over bins for O(1) window aggregation. Bin j spans
  // [j * binWidthSec, (j + 1) * binWidthSec).
  const n = bins.length;
  const prefReceived = new Float64Array(n + 1);
  const prefExpected = new Float64Array(n + 1);
  for (let j = 0; j < n; j++) {
    prefReceived[j + 1] = prefReceived[j] + bins[j].count;
    prefExpected[j + 1] = prefExpected[j] + bins[j].expected;
  }

  const half = LOSS_RATE_WINDOW_SEC / 2;
  for (let i = 0; i < numPoints; i++) {
    const center = i * LOSS_RATE_STEP_SEC;
    const lo = Math.max(0, Math.floor((center - half) / binWidthSec));
    const hi = Math.min(n, Math.ceil((center + half) / binWidthSec));
    if (hi <= lo) continue;
    const received = prefReceived[hi] - prefReceived[lo];
    const expected = prefExpected[hi] - prefExpected[lo];
    if (expected <= 0) continue;
    ys[i] = Math.min(100, Math.max(0, 1 - received / expected) * 100);
  }
  return ys;
}

/** Builds aligned uPlot data (xs followed by one ys per topic) for the Loss Rate chart. */
export function buildLossRateData(
  topics: TimelineTopic[],
  selectedTopic: string | null,
  durationSec: number,
  binWidthSec: number,
): uPlot.AlignedData {
  const filtered = selectedTopic ? topics.filter((t) => t.name === selectedTopic) : topics;
  if (filtered.length === 0 || durationSec <= 0) return [new Float64Array(0)];

  const numPoints = Math.max(1, Math.ceil(durationSec / LOSS_RATE_STEP_SEC) + 1);
  const xs = new Float64Array(numPoints);
  for (let i = 0; i < numPoints; i++) {
    xs[i] = i * LOSS_RATE_STEP_SEC;
  }

  const series: (Float64Array | number[])[] = [xs];
  for (const topic of filtered) {
    series.push(buildTopicLossRateSeries(topic, numPoints, binWidthSec));
  }
  return series as uPlot.AlignedData;
}
