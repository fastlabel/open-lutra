import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockToggle } = vi.hoisted(() => ({ mockToggle: vi.fn() }));

vi.mock("../store", () => ({
  useRecordingStore: {
    getState: () => ({ toggle: mockToggle }),
  },
}));

import { useRecordShortcut } from "../use-record-shortcut";

function dispatchSpace(): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { code: "Space", cancelable: true, bubbles: true });
  document.dispatchEvent(event);
  return event;
}

/** The shared listener and focus rule are covered by use-page-shortcut / keyboard; this is the wiring. */
describe("useRecordShortcut", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("toggles recording on a plain Space and prevents the default scroll", () => {
    renderHook(() => useRecordShortcut());

    const event = dispatchSpace();

    expect(mockToggle).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("is always live, so Space reaches recording without a further gate", () => {
    renderHook(() => useRecordShortcut());

    dispatchSpace();
    dispatchSpace();

    expect(mockToggle).toHaveBeenCalledTimes(2);
  });

  it("removes the listener on unmount", () => {
    const { unmount } = renderHook(() => useRecordShortcut());

    unmount();
    dispatchSpace();

    expect(mockToggle).not.toHaveBeenCalled();
  });
});
