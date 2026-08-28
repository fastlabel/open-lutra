/** Keyboard shortcut: Space toggles recording start/stop, mirroring the Record button.
 *
 * Mounted by RecordButton, which renders only on the recorder page, so the shortcut is
 * scoped to that page and torn down on navigation. Targets hands-free operation (e.g. a
 * foot pedal that emits Space) per issue #34.
 *
 * Space belongs to the recorder page: the listener runs in the capture phase and cancels the
 * default, so buttons, checkboxes and switches never consume it — clicking a toggle leaves
 * focus on it, and the next Space must still reach recording. Cancelling the keydown default
 * also suppresses the native Space-to-click, so a focused Record button toggles once.
 */
import { useEffect } from "react";
import { useRecordingStore } from "./store";

/** True when focus is on an element that needs Space for its own input. */
function ownsSpace(el: Element | null): boolean {
  if (!el) return false;
  if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return true;
  // Editable text hosts, plus popovers and dialogs (metadata panel, confirmations) that run
  // their own keyboard handling — the shortcut would fire behind the open layer.
  return (
    el.closest(
      '[role="textbox"], [contenteditable]:not([contenteditable="false"]), [role="dialog"], [role="alertdialog"]',
    ) !== null
  );
}

export function useRecordShortcut(): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
      // Skip while typing or while an overlay owns the keyboard.
      if (ownsSpace(document.activeElement)) return;
      // Suppress the page scroll and any activation of the focused control.
      e.preventDefault();
      useRecordingStore.getState().toggle();
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, []);
}
