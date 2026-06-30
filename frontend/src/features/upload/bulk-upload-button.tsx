/** Bulk upload action for the recordings list page.
 *
 * Mounted next to <BulkDeleteButton /> in the recordings table toolbar. Reads
 * the selected folder set from useRecordingsStore.checkedFolders and fires
 * POST /api/upload/start-bulk. Per-folder upload progress flows through the
 * SSE job stream, so this component does not track in-flight state per row —
 * the UploadBadge on each recording row picks that up.
 *
 * Rendered disabled with an explanatory tooltip when upload_enabled is false
 * on /api/config (no upload destination configured), mirroring the
 * single-recording UploadButton. Still hidden when no folder is selected.
 */

import { CloudUpload, Loader2 } from "lucide-react";
import type { BulkUploadResponse } from "@/api/generated/schemas";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRecordingsStore } from "@/features/recordings";
import { useConfig, useStartBulkUpload } from "@/hooks/use-api";
import { useAddLog } from "@/hooks/use-topics-stream";

export function BulkUploadButton() {
  const { data: config } = useConfig();
  const checkedFolders = useRecordingsStore((s) => s.checkedFolders);
  const clearChecked = useRecordingsStore((s) => s.clearChecked);
  const startBulkUpload = useStartBulkUpload();
  const addLog = useAddLog();

  if (checkedFolders.size === 0) return null;

  const uploadEnabled = !!config?.upload_enabled;

  const handleClick = () => {
    const folders = [...checkedFolders];
    startBulkUpload.mutate(
      { data: { folders } },
      {
        onSuccess: (resp) => {
          const body = resp.status === 200 ? (resp.data as BulkUploadResponse) : null;
          if (!body) {
            addLog("danger", "Bulk upload failed: unexpected response");
            return;
          }
          const failed = body.results.filter((r) => r.status === "failed");
          const enqueued = body.results.length - failed.length;
          addLog("info", `Enqueued ${enqueued} upload${enqueued === 1 ? "" : "s"}`);
          for (const f of failed) {
            addLog("danger", `Upload skipped for ${f.folder}: ${f.error ?? "unknown error"}`);
          }
          clearChecked();
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Bulk upload failed";
          addLog("danger", `Bulk upload failed: ${msg}`);
        },
      },
    );
  };

  const button = (
    <button
      type="button"
      disabled={!uploadEnabled || startBulkUpload.isPending}
      onClick={handleClick}
      className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-emerald-300 transition-colors enabled:hover:bg-emerald-500/20 disabled:pointer-events-none disabled:text-muted-foreground/40"
    >
      {startBulkUpload.isPending ? <Loader2 size={13} className="animate-spin" /> : <CloudUpload size={13} />}
      Upload
    </button>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* The disabled button has pointer-events:none, so wrap it in a span
            that receives the hover the tooltip needs to open. */}
        {uploadEnabled ? button : <span className="cursor-not-allowed">{button}</span>}
      </TooltipTrigger>
      <TooltipContent side="bottom">
        {uploadEnabled
          ? `Upload ${checkedFolders.size} item${checkedFolders.size === 1 ? "" : "s"}`
          : "No upload destination is configured"}
      </TooltipContent>
    </Tooltip>
  );
}
