/** Inline icon shown on a recording row to surface the latest upload state.
 *
 * Reserves a fixed-width slot so titles stay aligned across rows, matching
 * `ValidationBadge`. The slot is empty when no upload has ever been attempted.
 *
 * Reads the persisted state from `FileEntry.upload_status` (already part of
 * the recordings list response, so this badge does not trigger any extra HTTP
 * traffic) and overlays the live job-stream progress when an upload is in
 * flight for this folder.
 *
 * Hidden entirely when `upload_enabled` is false on `/api/config`.
 */

import { CloudCheck, CloudOff, Loader2 } from "lucide-react";
import type { FileEntry } from "@/api/generated/schemas";
import { useConfig } from "@/hooks/use-api";
import { useJobs } from "@/hooks/use-jobs-stream";

export function UploadBadge({ entry }: { entry: FileEntry }) {
  // --- Server state ---
  const { data: config } = useConfig();
  const jobs = useJobs();

  if (!config?.upload_enabled) return null;

  const activeJob = jobs.find(
    (j) => j.type === "upload" && j.folder === entry.name && (j.status === "queued" || j.status === "running"),
  );

  if (activeJob) {
    const { current, total } = activeJob.progress;
    const percent = total > 0 ? Math.min(100, Math.floor((current / total) * 100)) : 0;
    return (
      <span
        className="inline-flex shrink-0 items-center gap-1 text-[13px] text-muted-foreground"
        data-status="uploading"
        title={`Uploading ${percent}%`}
      >
        <Loader2 size={14} className="animate-spin" />
        <span className="tabular-nums">{percent}%</span>
      </span>
    );
  }

  if (entry.upload_status === "uploaded") {
    return (
      <span
        className="inline-flex h-4 w-4 shrink-0 items-center justify-center"
        data-status="uploaded"
        title="Uploaded"
      >
        <CloudCheck size={14} className="text-emerald-300" />
      </span>
    );
  }

  if (entry.upload_status === "failed") {
    return (
      <span
        className="inline-flex h-4 w-4 shrink-0 items-center justify-center"
        data-status="failed"
        title="Upload failed"
      >
        <CloudOff size={14} className="text-red-300" />
      </span>
    );
  }

  // idle / not_found / null — reserve an empty slot so row contents stay aligned.
  return <span className="inline-flex h-4 w-4 shrink-0" />;
}
