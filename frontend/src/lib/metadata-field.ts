/** Helpers for master-defined recording metadata fields. */

/**
 * Whether `value` satisfies the field's regex `pattern`.
 *
 * An empty value, an absent pattern, and a malformed (uncompilable) pattern all
 * count as valid: empty means "not entered yet" and a bad config-provided regex
 * should not trap the operator.
 */
export function matchesPattern(pattern: string | null | undefined, value: string): boolean {
  if (!pattern || value === "") return true;
  try {
    return new RegExp(pattern).test(value);
  } catch {
    return true;
  }
}
