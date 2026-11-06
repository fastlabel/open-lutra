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
  it("advances to the next day just after local midnight", () => {
    vi.setSystemTime(new Date(2026, 10, 6, 23, 59, 0));
    const { result } = renderHook(() => useLocalDay());
    expect(result.current.getDate()).toBe(6);

    act(() => {
      vi.advanceTimersByTime(59_000);
    });
    expect(result.current.getDate()).toBe(6);

    act(() => {
      vi.advanceTimersByTime(2_000);
    });
    expect(result.current.getDate()).toBe(7);
  });

  it("re-arms the timer after each rollover", () => {
    vi.setSystemTime(new Date(2026, 10, 6, 23, 59, 0));
    const { result } = renderHook(() => useLocalDay());

    act(() => {
      vi.advanceTimersByTime(61_000);
    });
    expect(result.current.getDate()).toBe(7);

    act(() => {
      vi.advanceTimersByTime(24 * 60 * 60 * 1000);
    });
    expect(result.current.getDate()).toBe(8);
  });

  it("clears the pending timer on unmount", () => {
    vi.setSystemTime(new Date(2026, 10, 6, 12, 0, 0));
    const { unmount } = renderHook(() => useLocalDay());
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
