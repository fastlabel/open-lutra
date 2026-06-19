/** Keyboard shortcut: Space toggles recording start/stop, mirroring the Record button.
 *
 * Mounted by RecordButton, which renders only on the recorder page, so the shortcut is
 * scoped to that page and torn down on navigation. Targets hands-free operation (e.g. a
 * foot pedal that emits Space) per issue #34.
 */
import { useEffect } from "react";
import { useRecordingStore } from "./store";

/** True when focus is on an element that natively consumes Space or text input. */
function isInteractiveTarget(el: Element | null): boolean {
  if (!el) return false;
  if (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement ||
    el instanceof HTMLButtonElement
  ) {
    return true;
  }
  if (el instanceof HTMLElement && el.isContentEditable) return true;
  return el.closest('[role="button"], [role="textbox"]') !== null;
}

export function useRecordShortcut(): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
      // Skip while typing or when an element already handles Space (also avoids a double-toggle
      // when the Record button itself is focused — its native Space click handles that case).
      if (isInteractiveTarget(document.activeElement)) return;
      // Space owns the recorder page; suppress the default page scroll.
      e.preventDefault();
      useRecordingStore.getState().toggle();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}
