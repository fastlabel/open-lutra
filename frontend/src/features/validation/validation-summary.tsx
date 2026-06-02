/** Validation summary panel: per-validator pass/warn/fail/error results.
 *
 * Lives in the recording detail page alongside the quality summary. The
 * recording's first visit triggers a run via POST /api/validation/analyze
 * (idempotent) so users do not have to push a button to see results.
 */

import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { ValidationResponse, ValidationResultItem } from "@/api/generated/schemas";
import { useStartValidation, useValidation } from "@/hooks/use-api";
import { isValidationStatus, ValidationStatusBadge } from "./ui/status-badge";

/** Status helper for the panel container. The `ready + report` case is handled
 * by the main render path, so this only covers the empty / pending / error
 * variants.
 */
function StatusMessage({
  selectedFolder,
  data,
  isLoading,
}: {
  selectedFolder: string | null;
  data: ValidationResponse | undefined;
  isLoading: boolean;
}) {
  if (!selectedFolder) {
    return (
      <p className="p-3 text-center text-[13px] text-muted-foreground">Select a recording to see validation results.</p>
    );
  }
  if (isLoading || data?.status === "analyzing") {
    return (
      <div className="flex items-center justify-center gap-2 px-3 py-6 text-[13px] text-muted-foreground">
        <Loader2 size={14} className="animate-spin" />
        <span>Running validators...</span>
      </div>
    );
  }
  if (data?.status === "error") {
    return <p className="px-3 py-3 text-[13px] text-red-400/80">Validation error: {data.error}</p>;
  }
  return <p className="px-3 py-3 text-[13px] text-muted-foreground">No validation results yet.</p>;
}

function ValidationResultRow({ item }: { item: ValidationResultItem }) {
  // --- Render-only state ---
  const [expanded, setExpanded] = useState(false);

  const status = isValidationStatus(item.status) ? item.status : "error";
  const hasDetails = item.details !== null && Object.keys(item.details).length > 0;
  const Chevron = expanded ? ChevronDown : ChevronRight;

  const header = (
    <div className="flex items-start gap-2 px-3 py-2 text-left">
      <div className="pt-0.5">
        {hasDetails ? (
          <Chevron size={12} className="text-muted-foreground" aria-hidden="true" />
        ) : (
          <span className="inline-block h-3 w-3" aria-hidden="true" />
        )}
      </div>
      <div className="pt-0.5">
        <ValidationStatusBadge status={status} size="sm" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] font-medium text-foreground" title={item.validator_name}>
            {item.validator_name}
          </span>
          {item.source === "custom" && (
            <span
              className="rounded bg-muted/50 px-1 text-[13px] text-muted-foreground"
              title={item.source_module ?? "custom"}
            >
              custom
            </span>
          )}
        </div>
        {item.message && <p className="mt-0.5 text-[13px] text-muted-foreground">{item.message}</p>}
      </div>
    </div>
  );

  return (
    <div className="border-b border-border last:border-b-0">
      {hasDetails ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="block w-full hover:bg-muted/20"
        >
          {header}
        </button>
      ) : (
        header
      )}
      {hasDetails && expanded && (
        <pre className="mx-3 mb-2 ml-9 overflow-x-auto whitespace-pre rounded bg-muted/40 px-2 py-1.5 text-[13px] text-muted-foreground">
          {JSON.stringify(item.details, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function ValidationSummary({
  selectedFolder,
  triggerAnalysis = false,
}: {
  selectedFolder: string | null;
  /** When true and no report exists yet, kick off POST /api/validation/analyze. */
  triggerAnalysis?: boolean;
}) {
  // --- Server state ---
  const { data, isLoading } = useValidation(selectedFolder);
  const { mutate: startAnalysis, isPending: isStartingAnalysis } = useStartValidation();

  // --- Side effects ---
  useEffect(() => {
    if (triggerAnalysis && selectedFolder && data?.status === "not_found" && !isStartingAnalysis) {
      startAnalysis({ params: { path: selectedFolder } });
    }
  }, [triggerAnalysis, selectedFolder, data?.status, isStartingAnalysis, startAnalysis]);

  if (!selectedFolder || data?.status !== "ready" || !data.report) {
    return <StatusMessage selectedFolder={selectedFolder} data={data} isLoading={isLoading} />;
  }

  const { report } = data;
  const overall = isValidationStatus(report.overall_status) ? report.overall_status : "error";

  return (
    <div className="space-y-3 p-3">
      {/* Overall status header */}
      <div className="flex items-center justify-between gap-2 rounded-md bg-muted/30 px-2.5 py-1.5">
        <span className="text-[13px] font-semibold uppercase tracking-wider text-muted-foreground">Validation</span>
        <ValidationStatusBadge status={overall} />
      </div>

      {/* Per-validator results */}
      {report.results.length === 0 ? (
        <p className="px-3 py-3 text-[13px] text-muted-foreground">No validators configured.</p>
      ) : (
        <div className="rounded-md border border-border overflow-hidden">
          {report.results.map((item) => (
            <ValidationResultRow key={item.validator_name} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
