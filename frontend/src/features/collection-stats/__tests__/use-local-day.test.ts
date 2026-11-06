import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLocalDay } from "../use-local-day";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useLocalDay", () => {
  it("advances to the next day at the first check after local midnight", () => {
    vi.setSystemTime(new Date(2026, 10, 6, 23, 59, 30));
    const { result } = renderHook(() => useLocalDay());
    expect(result.current.getDate()).toBe(6);

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(result.current.getDate()).toBe(7);
  });

  it("keeps the same value while the date is unchanged", () => {
    vi.setSystemTime(new Date(2026, 10, 6, 12, 0, 0));
    const { result } = renderHook(() => useLocalDay());
    const first = result.current;

    act(() => {
      vi.advanceTimersByTime(10 * 60_000);
    });
    expect(result.current).toBe(first);
  });

  it("catches up within a minute when the clock jumps past midnight (e.g. after sleep)", () => {
    vi.setSystemTime(new Date(2026, 10, 6, 18, 0, 0));
    const { result } = renderHook(() => useLocalDay());

    // Sleep: wall-clock time moves on, but pending timers have not run.
    vi.setSystemTime(new Date(2026, 10, 7, 9, 0, 0));
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(result.current.getDate()).toBe(7);
  });

  it("clears the interval on unmount", () => {
    vi.setSystemTime(new Date(2026, 10, 6, 12, 0, 0));
    const { unmount } = renderHook(() => useLocalDay());
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
