/** Pure helpers for the timeline heatmap's count-based deficit shading.
 *
 * Each bin is colored by how far its received message count falls below the expected count
 * (which already reflects the configured expected_hz). The per-bin ratio is noisy at the 50ms
 * bin scale, so it is smoothed over a ~1s window — matching the Loss Rate chart — before being
 * mapped to a green→amber→red gradient anchored at the 2% / 5% warn/danger thresholds.
 */

import type { TimelineBin } from "@/api/generated/schemas";

/** Smoothing window (seconds), matching the Loss Rate chart so both views agree. */
export const SMOOTH_WINDOW_SEC = 1.0;

/** Deficit at/below which a bin is fully green (warn threshold). */
const WARN = 0.02;
/** Deficit at which a bin reaches amber (danger threshold). */
const DANGER = 0.05;
/** Deficit at/above which a bin is fully red. */
const RED_CAP = 0.2;

// Gradient anchor colors (emerald-400 / amber-400 / red-400) and shared alpha.
const GREEN: [number, number, number] = [52, 211, 153];
const AMBER: [number, number, number] = [251, 191, 36];
const RED: [number, number, number] = [248, 113, 113];
const ALPHA = 0.5;

/** Neutral fill for topics without an expected rate (deficit is undefined). */
export const NO_RATE_COLOR = "rgba(120, 120, 120, 0.12)";

/** Per-bin smoothed deficit (0..1): 1 − received / expected over a ~SMOOTH_WINDOW_SEC window
 * centered on each bin. Bins are contiguous with `binWidthSec` spacing, so the window is a
 * fixed number of bins on each side. */
export function computeSmoothedDeficits(bins: TimelineBin[], binWidthSec: number): Float64Array {
  const n = bins.length;
  const out = new Float64Array(n);
  if (n === 0 || binWidthSec <= 0) return out;

  const prefReceived = new Float64Array(n + 1);
  const prefExpected = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) {
    prefReceived[i + 1] = prefReceived[i] + bins[i].count;
    prefExpected[i + 1] = prefExpected[i] + bins[i].expected;
  }

  const half = Math.max(1, Math.round(SMOOTH_WINDOW_SEC / 2 / binWidthSec));
  for (let i = 0; i < n; i++) {
    const lo = Math.max(0, i - half);
    const hi = Math.min(n, i + half + 1);
    const received = prefReceived[hi] - prefReceived[lo];
    const expected = prefExpected[hi] - prefExpected[lo];
    out[i] = expected > 0 ? Math.max(0, 1 - received / expected) : 0;
  }
  return out;
}

function mix(a: [number, number, number], b: [number, number, number], t: number): string {
  const r = Math.round(a[0] + (b[0] - a[0]) * t);
  const g = Math.round(a[1] + (b[1] - a[1]) * t);
  const bl = Math.round(a[2] + (b[2] - a[2]) * t);
  return `rgba(${r}, ${g}, ${bl}, ${ALPHA})`;
}

/** Maps a deficit (0..1) to a gradient color: green up to the 2% warn threshold, blending to
 * amber at 5% (danger), then to full red by RED_CAP. */
export function deficitColor(deficit: number): string {
  const d = Math.max(0, Math.min(1, deficit));
  if (d <= WARN) return mix(GREEN, GREEN, 0);
  if (d < DANGER) return mix(GREEN, AMBER, (d - WARN) / (DANGER - WARN));
  if (d < RED_CAP) return mix(AMBER, RED, (d - DANGER) / (RED_CAP - DANGER));
  return mix(RED, RED, 0);
}
