import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockToggle } = vi.hoisted(() => ({ mockToggle: vi.fn() }));

vi.mock("../store", () => ({
  useRecordingStore: {
    getState: () => ({ toggle: mockToggle }),
  },
}));

import { useRecordShortcut } from "../use-record-shortcut";

function dispatchSpace(init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { code: "Space", cancelable: true, ...init });
  document.dispatchEvent(event);
  return event;
}

describe("useRecordShortcut", () => {
  afterEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = "";
  });

  it("toggles recording on a plain Space and prevents the default scroll", () => {
    renderHook(() => useRecordShortcut());

    const event = dispatchSpace();

    expect(mockToggle).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("ignores Space combined with a modifier key", () => {
    renderHook(() => useRecordShortcut());

    dispatchSpace({ ctrlKey: true });

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("ignores auto-repeat (held key)", () => {
    renderHook(() => useRecordShortcut());

    dispatchSpace({ repeat: true });

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("ignores keys other than Space", () => {
    renderHook(() => useRecordShortcut());

    document.dispatchEvent(new KeyboardEvent("keydown", { code: "Enter", cancelable: true }));

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("does not fire while a text input is focused", () => {
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    renderHook(() => useRecordShortcut());

    dispatchSpace();

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("does not fire while a button is focused (its native Space click handles it)", () => {
    const button = document.createElement("button");
    document.body.appendChild(button);
    button.focus();
    renderHook(() => useRecordShortcut());

    dispatchSpace();

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("removes the listener on unmount", () => {
    const { unmount } = renderHook(() => useRecordShortcut());

    unmount();
    dispatchSpace();

    expect(mockToggle).not.toHaveBeenCalled();
  });
});
