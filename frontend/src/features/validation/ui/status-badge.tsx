/** Compact pill rendering a validation status (pass / warn / fail / error).
 *
 * Used both inside the detail-page summary and inline next to each recording
 * row, so the same colour vocabulary appears everywhere validation surfaces.
 */

import { AlertTriangle, CheckCircle2, CircleAlert, XCircle } from "lucide-react";
import type { ComponentType } from "react";

type Status = "pass" | "warn" | "fail" | "error";

const STATUS_META: Record<
  Status,
  { label: string; icon: ComponentType<{ size?: number; className?: string }>; classes: string }
> = {
  pass: {
    label: "Pass",
    icon: CheckCircle2,
    classes: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
  },
  warn: {
    label: "Warn",
    icon: AlertTriangle,
    classes: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
  },
  fail: {
    label: "Fail",
    icon: XCircle,
    classes: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/30",
  },
  error: {
    label: "Error",
    icon: CircleAlert,
    classes: "bg-purple-500/15 text-purple-700 dark:text-purple-300 border-purple-500/30",
  },
};

/** Returns true when `value` is one of the known validation statuses. */
export function isValidationStatus(value: string | null | undefined): value is Status {
  return value === "pass" || value === "warn" || value === "fail" || value === "error";
}

export function ValidationStatusBadge({ status, size = "md" }: { status: Status; size?: "sm" | "md" }) {
  const meta = STATUS_META[status];
  const Icon = meta.icon;
  const padding = size === "sm" ? "px-1.5 py-0 text-[13px]" : "px-2 py-0.5 text-[13px]";
  const iconSize = size === "sm" ? 12 : 13;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border ${padding} font-medium ${meta.classes}`}
      data-status={status}
    >
      <Icon size={iconSize} className="shrink-0" />
      {meta.label}
    </span>
  );
}
