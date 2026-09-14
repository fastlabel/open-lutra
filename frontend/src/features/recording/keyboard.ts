/** Focus rule shared by the recorder page's keyboard shortcuts.
 *
 * The rule describes the focus context only, never the key: a shortcut yields when focus is in a
 * text-entry context or behind an overlay, and otherwise belongs to the page. Per-key exceptions
 * (a printable character competing with `<select>` typeahead, arrows yielding to a listbox) stay
 * at the call site, so this stays one rule instead of a flag matrix.
 */

/** True when focus is on an element that needs the key for its own input. */
export function ownsKeyboard(el: Element | null): boolean {
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
