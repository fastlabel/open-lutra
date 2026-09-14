import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePageShortcut } from "../use-page-shortcut";

function dispatch(code: string, init: KeyboardEventInit = {}, target: EventTarget = document): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { code, cancelable: true, bubbles: true, ...init });
  target.dispatchEvent(event);
  return event;
}

/** Focus a freshly mounted element of the given tag, mirroring a click on a page control. */
function focusElement(tag: string): HTMLElement {
  const el = document.createElement(tag);
  document.body.appendChild(el);
  el.focus();
  return el;
}

describe("usePageShortcut", () => {
  afterEach(() => {
    vi.clearAllMocks();
    document.body.innerHTML = "";
  });

  it("fires on the configured code and prevents the default", () => {
    const onFire = vi.fn();
    renderHook(() => usePageShortcut({ code: "KeyE", onFire }));

    const event = dispatch("KeyE");

    expect(onFire).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("ignores other codes", () => {
    const onFire = vi.fn();
    renderHook(() => usePageShortcut({ code: "KeyE", onFire }));

    dispatch("Space");

    expect(onFire).not.toHaveBeenCalled();
  });

  it.each(["ctrlKey", "metaKey", "altKey", "shiftKey"])("ignores the code combined with %s", (modifier) => {
    const onFire = vi.fn();
    renderHook(() => usePageShortcut({ code: "Space", onFire }));

    dispatch("Space", { [modifier]: true });

    expect(onFire).not.toHaveBeenCalled();
  });

  it("ignores auto-repeat (held key)", () => {
    const onFire = vi.fn();
    renderHook(() => usePageShortcut({ code: "Space", onFire }));

    dispatch("Space", { repeat: true });

    expect(onFire).not.toHaveBeenCalled();
  });

  it("leaves the key to a focused element that owns the keyboard", () => {
    const onFire = vi.fn();
    const input = focusElement("input");
    renderHook(() => usePageShortcut({ code: "Space", onFire }));

    const event = dispatch("Space", {}, input);

    expect(onFire).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("fires ahead of the focused control, cancelling its native activation", () => {
    const onFire = vi.fn();
    const button = focusElement("button");
    const onClick = vi.fn();
    button.addEventListener("click", onClick);
    renderHook(() => usePageShortcut({ code: "Space", onFire }));

    const event = dispatch("Space", {}, button);

    expect(onFire).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("registers no listener while disabled, leaving the key to the rest of the page", () => {
    const onFire = vi.fn();
    renderHook(() => usePageShortcut({ code: "Space", enabled: false, onFire }));

    const event = dispatch("Space");

    expect(onFire).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("registers and unregisters as enabled flips", () => {
    const onFire = vi.fn();
    const { rerender } = renderHook(({ enabled }) => usePageShortcut({ code: "Space", enabled, onFire }), {
      initialProps: { enabled: false },
    });

    rerender({ enabled: true });
    dispatch("Space");
    expect(onFire).toHaveBeenCalledTimes(1);

    rerender({ enabled: false });
    dispatch("Space");
    expect(onFire).toHaveBeenCalledTimes(1);
  });

  it("calls the latest onFire, so callers do not have to memoize it", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ onFire }) => usePageShortcut({ code: "Space", onFire }), {
      initialProps: { onFire: first },
    });

    rerender({ onFire: second });
    dispatch("Space");

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });

  it("removes the listener on unmount", () => {
    const onFire = vi.fn();
    const { unmount } = renderHook(() => usePageShortcut({ code: "Space", onFire }));

    unmount();
    dispatch("Space");

    expect(onFire).not.toHaveBeenCalled();
  });
});
