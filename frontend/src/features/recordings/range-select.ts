/** Shift+click range selection over the recordings list, following the order the rows are displayed in. */

/** The checked set after Shift+clicking `target` with `anchor` as the range start.
 *
 * Every row between the anchor and the target (inclusive) takes the anchor's current state, so a range can be
 * checked or unchecked in one click. Returns null when there is no usable anchor (none yet, or it is not among the
 * displayed rows), in which case the click is handled as a plain toggle.
 */
export function applyRange(
  checked: ReadonlySet<string>,
  displayed: readonly string[],
  anchor: string | null,
  target: string,
): Set<string> | null {
  const from = anchor === null ? -1 : displayed.indexOf(anchor);
  const to = displayed.indexOf(target);
  if (from === -1 || to === -1) return null;

  const next = new Set(checked);
  const select = checked.has(displayed[from]);
  for (const folder of displayed.slice(Math.min(from, to), Math.max(from, to) + 1)) {
    if (select) next.add(folder);
    else next.delete(folder);
  }
  return next;
}
