/** Listener boilerplate shared by the recorder page's keyboard shortcuts.
 *
 * A page shortcut belongs to the page rather than to the focused element: the listener runs in
 * the capture phase and cancels the default, so buttons, checkboxes and switches never consume
 * the key — clicking a toggle leaves focus on it, and the next press must still reach the page.
 * Modifier combinations and auto-repeat (a held key) are rejected, and `ownsKeyboard` decides
 * when focus takes the key back.
 *
 * What the key does, and when it is allowed to run, stays with the caller.
 */

import { useEffect, useRef } from "react";
import { ownsKeyboard } from "./keyboard";

interface PageShortcutParams {
  /** KeyboardEvent.code — "Space", "KeyE", … */
  code: string;
  /**
   * Register the listener only while the action can actually run. Gating inside `onFire`
   * instead would leave the listener registered and still cancel the default, swallowing the
   * key from the rest of the page.
   */
  enabled?: boolean;
  /** Read at fire time, so callers do not have to memoize it. */
  onFire: () => void;
}

export function usePageShortcut({ code, enabled = true, onFire }: PageShortcutParams): void {
  const onFireRef = useRef(onFire);
  useEffect(() => {
    onFireRef.current = onFire;
  });

  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== code || e.repeat) return;
      if (e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
      // Skip while typing or while an overlay owns the keyboard.
      if (ownsKeyboard(document.activeElement)) return;
      // Suppress the page scroll and any activation of the focused control.
      e.preventDefault();
      onFireRef.current();
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => document.removeEventListener("keydown", onKeyDown, true);
  }, [code, enabled]);
}
