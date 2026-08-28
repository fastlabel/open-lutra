import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockToggle } = vi.hoisted(() => ({ mockToggle: vi.fn() }));

vi.mock("../store", () => ({
  useRecordingStore: {
    getState: () => ({ toggle: mockToggle }),
  },
}));

import { useRecordShortcut } from "../use-record-shortcut";

function dispatchSpace(init: KeyboardEventInit = {}, target: EventTarget = document): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { code: "Space", cancelable: true, bubbles: true, ...init });
  target.dispatchEvent(event);
  return event;
}

/** Focus a freshly mounted element of the given tag, mirroring a click on a page control. */
function focusElement(tag: string, attributes: Record<string, string> = {}): HTMLElement {
  const el = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) el.setAttribute(name, value);
  document.body.appendChild(el);
  el.focus();
  return el;
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
    const input = focusElement("input");
    renderHook(() => useRecordShortcut());

    dispatchSpace({}, input);

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("does not fire while a textarea is focused", () => {
    const textarea = focusElement("textarea");
    renderHook(() => useRecordShortcut());

    dispatchSpace({}, textarea);

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("does not fire while a contenteditable element is focused", () => {
    const editable = focusElement("div", { contenteditable: "true", tabindex: "0" });
    renderHook(() => useRecordShortcut());

    dispatchSpace({}, editable);

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("does not fire while focus is inside an open popover or dialog", () => {
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    document.body.appendChild(dialog);
    const select = document.createElement("select");
    dialog.appendChild(select);
    select.focus();
    renderHook(() => useRecordShortcut());

    dispatchSpace({}, select);

    expect(mockToggle).not.toHaveBeenCalled();
  });

  it("fires while a button is focused and cancels its native activation", () => {
    const button = focusElement("button");
    renderHook(() => useRecordShortcut());

    const event = dispatchSpace({}, button);

    expect(mockToggle).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("fires while a clicked toggle keeps focus (checkbox / switch render as buttons)", () => {
    const toggle = focusElement("button", { role: "switch", "aria-checked": "false" });
    renderHook(() => useRecordShortcut());

    dispatchSpace({}, toggle);

    expect(mockToggle).toHaveBeenCalledTimes(1);
  });

  it("fires while a select is focused, so the delay dropdown does not swallow Space", () => {
    const select = focusElement("select");
    renderHook(() => useRecordShortcut());

    dispatchSpace({}, select);

    expect(mockToggle).toHaveBeenCalledTimes(1);
  });

  it("removes the listener on unmount", () => {
    const { unmount } = renderHook(() => useRecordShortcut());

    unmount();
    dispatchSpace();

    expect(mockToggle).not.toHaveBeenCalled();
  });
});
