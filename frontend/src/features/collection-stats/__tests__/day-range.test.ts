import { afterEach, describe, expect, it, vi } from "vitest";
import { localDayRange, toLocalRfc3339 } from "../day-range";

const RFC3339_MIDNIGHT = /^\d{4}-\d{2}-\d{2}T00:00:00[+-]\d{2}:\d{2}$/;

afterEach(() => {
  vi.restoreAllMocks();
});

describe("localDayRange", () => {
  it("spans from today's local midnight to tomorrow's local midnight", () => {
    const now = new Date(2026, 10, 6, 14, 30, 15);
    const { started_after, started_before } = localDayRange(now);

    expect(started_after).toMatch(RFC3339_MIDNIGHT);
    expect(started_before).toMatch(RFC3339_MIDNIGHT);
    // The offset makes each string resolve to the exact local-midnight instant.
    expect(new Date(started_after).getTime()).toBe(new Date(2026, 10, 6).getTime());
    expect(new Date(started_before).getTime()).toBe(new Date(2026, 10, 7).getTime());
  });

  it("puts 23:50 yesterday outside today and 00:05 today inside it", () => {
    const today = localDayRange(new Date(2026, 10, 6, 0, 5));
    const yesterday = localDayRange(new Date(2026, 10, 5, 23, 50));

    // Adjacent days share a boundary (half-open intervals), so nothing is counted twice or dropped.
    expect(yesterday.started_before).toBe(today.started_after);
    const after = new Date(today.started_after).getTime();
    expect(new Date(2026, 10, 5, 23, 50).getTime()).toBeLessThan(after);
    expect(new Date(2026, 10, 6, 0, 5).getTime()).toBeGreaterThanOrEqual(after);
  });

  it("rolls over month and year boundaries", () => {
    const { started_after, started_before } = localDayRange(new Date(2026, 11, 31, 12));
    expect(started_after.startsWith("2026-12-31T00:00:00")).toBe(true);
    expect(started_before.startsWith("2027-01-01T00:00:00")).toBe(true);
  });
});

describe("toLocalRfc3339", () => {
  it.each([
    [-540, "+09:00"],
    [0, "+00:00"],
    [300, "-05:00"],
    [-330, "+05:30"],
  ])("formats a getTimezoneOffset of %i as %s", (tzOffset, expected) => {
    vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(tzOffset);
    expect(toLocalRfc3339(new Date(2026, 0, 2, 3, 4, 5))).toBe(`2026-01-02T03:04:05${expected}`);
  });
});
