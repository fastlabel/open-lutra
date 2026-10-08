/** Inline icon shown on a recording row to surface the validation outcome.
 *
 * Always renders a fixed-width slot so titles stay aligned across rows. The
 * slot is empty when validation has not finished yet or when the recording
 * predates the validation feature; otherwise it renders a status-specific
 * icon (including a check for `pass`).
 */

import { AlertTriangle, CheckCircle2, CircleAlert, XCircle } from "lucide-react";
import type { ComponentType } from "react";

type ValidationStatus = "pass" | "warn" | "fail" | "error";

const ICON_BY_STATUS: Record<
  ValidationStatus,
  { Icon: ComponentType<{ size?: number; className?: string }>; className: string; label: string }
> = {
  pass: { Icon: CheckCircle2, className: "text-emerald-700 dark:text-emerald-300", label: "Pass" },
  warn: { Icon: AlertTriangle, className: "text-amber-700 dark:text-amber-300", label: "Warn" },
  fail: { Icon: XCircle, className: "text-red-700 dark:text-red-300", label: "Fail" },
  error: { Icon: CircleAlert, className: "text-purple-700 dark:text-purple-300", label: "Error" },
};

function isValidationStatus(value: string | null): value is ValidationStatus {
  return value === "pass" || value === "warn" || value === "fail" || value === "error";
}

export function ValidationBadge({ status }: { status: string | null }) {
  const meta = isValidationStatus(status) ? ICON_BY_STATUS[status] : null;
  return (
    <span
      className="inline-flex h-4 w-4 shrink-0 items-center justify-center"
      data-status={meta ? status : undefined}
      title={meta?.label}
    >
      {meta && <meta.Icon size={14} className={meta.className} />}
    </span>
  );
}
