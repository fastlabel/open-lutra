import { describe, expect, it } from "vitest";
import type { TimelineBin, TimelineTopic } from "@/api/generated/schemas";
import { buildLossRateData, buildTopicLossRateSeries, LOSS_RATE_STEP_SEC } from "../loss-rate-utils";

const BIN_WIDTH = 0.05;

function bin(t: number, count: number, expected: number): TimelineBin {
  return { t, count, expected, has_gap: false, has_minor_loss: false };
}

/** N contiguous bins (BIN_WIDTH spacing from t=0) each with the given count/expected. */
function uniformBins(n: number, count: number, expected: number): TimelineBin[] {
  return Array.from({ length: n }, (_, i) => bin(i * BIN_WIDTH, count, expected));
}

function topic(expectedHz: number, bins: TimelineBin[]): TimelineTopic {
  return { name: "/test", msg_type: "std_msgs/msg/String", expected_hz: expectedHz, bins, gaps: [] };
}

const step = LOSS_RATE_STEP_SEC; // 0.1

describe("buildTopicLossRateSeries", () => {
  it("returns all zeros when there are no bins", () => {
    const ys = buildTopicLossRateSeries(topic(100, []), 50, BIN_WIDTH);
    expect(Array.from(ys)).toEqual(new Array(50).fill(0));
  });

  it("returns all zeros when expected_hz is 0", () => {
    const ys = buildTopicLossRateSeries(topic(0, uniformBins(40, 3, 5)), 40, BIN_WIDTH);
    expect(Array.from(ys).every((v) => v === 0)).toBe(true);
  });

  it("returns all zeros when binWidthSec is 0", () => {
    const ys = buildTopicLossRateSeries(topic(100, uniformBins(40, 3, 5)), 40, 0);
    expect(Array.from(ys).every((v) => v === 0)).toBe(true);
  });

  it("reports 0% loss when every bin is at its expected count", () => {
    const ys = buildTopicLossRateSeries(topic(100, uniformBins(40, 5, 5)), 40, BIN_WIDTH);
    // The window centered at 1.0s is fully inside the bin coverage.
    expect(ys[Math.round(1.0 / step)]).toBeCloseTo(0, 5);
  });

  it("reports a sustained deficit when the stream runs steadily below its rate", () => {
    // 3 of every 5 expected frames received → 40% loss, held across the whole stream.
    const ys = buildTopicLossRateSeries(topic(100, uniformBins(40, 3, 5)), 40, BIN_WIDTH);
    expect(ys[Math.round(1.0 / step)]).toBeCloseTo(40, 5);
  });

  it("localizes a single-bin loss to the windows overlapping it", () => {
    const bins = uniformBins(40, 5, 5);
    bins[20] = bin(20 * BIN_WIDTH, 4, 5); // 1 frame short at t=1.0s
    const ys = buildTopicLossRateSeries(topic(100, bins), 40, BIN_WIDTH);
    // Window at t=1.0 spans [0.5, 1.5): 1 missing frame out of 100 expected → 1%.
    expect(ys[Math.round(1.0 / step)]).toBeCloseTo(1, 5);
    // A window that does not overlap t=1.0 stays at 0.
    expect(ys[Math.round(0.1 / step)]).toBe(0);
  });

  it("caps the loss rate at 100%", () => {
    const ys = buildTopicLossRateSeries(topic(100, uniformBins(40, 0, 5)), 40, BIN_WIDTH);
    expect(ys[Math.round(1.0 / step)]).toBe(100);
  });
});

describe("buildLossRateData", () => {
  it("returns an empty xs array when there are no topics", () => {
    const result = buildLossRateData([], null, 10, BIN_WIDTH);
    expect(result.length).toBe(1);
    expect((result[0] as Float64Array).length).toBe(0);
  });

  it("returns an empty xs array when durationSec is 0", () => {
    const result = buildLossRateData([topic(100, uniformBins(40, 3, 5))], null, 0, BIN_WIDTH);
    expect((result[0] as Float64Array).length).toBe(0);
  });

  it("emits xs at STEP_SEC intervals covering durationSec", () => {
    const result = buildLossRateData([topic(100, uniformBins(20, 5, 5))], null, 1.0, BIN_WIDTH);
    const xs = result[0] as Float64Array;
    // ceil(1.0 / 0.1) + 1 = 11 points: 0.0, 0.1, ..., 1.0
    expect(xs.length).toBe(11);
    expect(xs[0]).toBe(0);
    expect(xs[xs.length - 1]).toBeCloseTo(1.0, 5);
  });

  it("filters to the selected topic only", () => {
    const t1 = { ...topic(100, uniformBins(20, 5, 5)), name: "/a" };
    const t2 = { ...topic(100, uniformBins(20, 5, 5)), name: "/b" };
    const result = buildLossRateData([t1, t2], "/b", 5, BIN_WIDTH);
    // [xs, ys for /b only]
    expect(result.length).toBe(2);
  });

  it("includes one ys series per topic when no topic is selected", () => {
    const t1 = { ...topic(100, uniformBins(20, 5, 5)), name: "/a" };
    const t2 = { ...topic(100, uniformBins(20, 5, 5)), name: "/b" };
    const result = buildLossRateData([t1, t2], null, 5, BIN_WIDTH);
    expect(result.length).toBe(3); // xs + 2 topics
  });
});
