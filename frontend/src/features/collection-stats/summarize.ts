/** Aggregate a day's recordings into the operator-facing collection summary.
 *
 * Only validated-usable recordings (`pass` / `warn`) feed the headline, so adding volume requires takes that
 * pass validation. `null` (no validation result) counts as pending. A result whose status this UI does not
 * recognize counts as a validation error, matching the validation panel, so a new backend status can never
 * inflate the usable figures.
 */

import type { FileEntry } from "@/api/generated/schemas";

export interface CollectionSummary {
  usable: { count: number; durationNs: number };
  total: number;
  failed: number;
  errors: number;
  pending: number;
}

export function summarize(entries: FileEntry[]): CollectionSummary {
  const summary: CollectionSummary = {
    usable: { count: 0, durationNs: 0 },
    total: 0,
    failed: 0,
    errors: 0,
    pending: 0,
  };
  for (const entry of entries) {
    summary.total += 1;
    switch (entry.validation_overall_status) {
      case "pass":
      case "warn":
        summary.usable.count += 1;
        summary.usable.durationNs += entry.duration_ns ?? 0;
        break;
      case "fail":
        summary.failed += 1;
        break;
      case null:
        summary.pending += 1;
        break;
      default:
        summary.errors += 1;
    }
  }
  return summary;
}
