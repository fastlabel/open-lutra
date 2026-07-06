import { describe, expect, it } from "vitest";
import type { TimelineBin } from "@/api/generated/schemas";
import { computeSmoothedDeficits, deficitColor } from "../heatmap-utils";

const BIN_WIDTH = 0.05;
const GREEN = "rgba(52, 211, 153, 0.5)";
const AMBER = "rgba(251, 191, 36, 0.5)";
const RED = "rgba(248, 113, 113, 0.5)";

function bin(t: number, count: number, expected: number): TimelineBin {
  return { t, count, expected, has_gap: false, has_minor_loss: false };
}

function channels(rgba: string): [number, number, number] {
  const m = rgba.match(/rgba\((\d+), (\d+), (\d+), [\d.]+\)/);
  if (!m) throw new Error(`unexpected rgba: ${rgba}`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function uniformBins(n: number, count: number, expected: number): TimelineBin[] {
  return Array.from({ length: n }, (_, i) => bin(i * BIN_WIDTH, count, expected));
}

describe("computeSmoothedDeficits", () => {
  it("returns an empty array for no bins", () => {
    expect(computeSmoothedDeficits([], BIN_WIDTH).length).toBe(0);
  });

  it("returns all zeros when binWidthSec is 0", () => {
    const out = computeSmoothedDeficits(uniformBins(40, 2, 5), 0);
    expect(Array.from(out).every((v) => v === 0)).toBe(true);
  });

  it("is 0 when every bin is at its expected count", () => {
    const out = computeSmoothedDeficits(uniformBins(40, 5, 5), BIN_WIDTH);
    for (const v of out) expect(v).toBeCloseTo(0, 5);
  });

  it("reflects a steady under-rate", () => {
    // Received 2 of every 4 expected → 50% deficit everywhere.
    const out = computeSmoothedDeficits(uniformBins(40, 2, 4), BIN_WIDTH);
    for (const v of out) expect(v).toBeCloseTo(0.5, 5);
  });

  it("smooths an isolated empty bin instead of showing 100% loss", () => {
    const bins = uniformBins(40, 5, 5);
    bins[20] = bin(20 * BIN_WIDTH, 0, 5); // a single empty bin at t=1.0s
    const out = computeSmoothedDeficits(bins, BIN_WIDTH);
    // Averaged over the ~1s window (21 bins): 1 − 100/105 ≈ 0.0476, not 1.0.
    expect(out[20]).toBeCloseTo(1 - 100 / 105, 4);
    // A bin far from the dip stays healthy.
    expect(out[0]).toBeCloseTo(0, 5);
  });
});

describe("deficitColor", () => {
  it("is green at or below the warn threshold", () => {
    expect(deficitColor(0)).toBe(GREEN);
    expect(deficitColor(0.02)).toBe(GREEN);
  });

  it("clamps negative input to green", () => {
    expect(deficitColor(-1)).toBe(GREEN);
  });

  it("is amber at the danger threshold", () => {
    expect(deficitColor(0.05)).toBe(AMBER);
  });

  it("is fully red at or above the cap", () => {
    expect(deficitColor(0.2)).toBe(RED);
    expect(deficitColor(1)).toBe(RED);
  });

  it("blends green→amber between the warn and danger thresholds", () => {
    // Between green (52, 211, 153) and amber (251, 191, 36).
    const c = channels(deficitColor(0.035));
    expect(c[0]).toBeGreaterThan(52); // red channel rises toward amber
    expect(c[0]).toBeLessThan(251);
    expect(c[2]).toBeLessThan(153); // blue channel falls toward amber
    expect(c[2]).toBeGreaterThan(36);
  });

  it("blends amber→red between the danger threshold and the cap", () => {
    // Between amber (251, 191, 36) and red (248, 113, 113).
    const c = channels(deficitColor(0.125));
    expect(c[1]).toBeLessThan(191); // green channel falls toward red
    expect(c[1]).toBeGreaterThan(113);
    expect(c[2]).toBeGreaterThan(36); // blue channel rises toward red
    expect(c[2]).toBeLessThan(113);
  });
});
