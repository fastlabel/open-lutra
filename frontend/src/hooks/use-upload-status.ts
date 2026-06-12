/**
 * Live upload status for a single recording folder.
 *
 * Fuses two sources so callers do not have to:
 *
 * 1. The persisted `upload_state.json` (via `useUpload`) — the source of
 *    truth between sessions.
 * 2. The SSE job stream (via `useJobs`) — gives a per-byte `percent`
 *    while an upload is in flight, faster than the refetch interval.
 *
 * While an `UploadJob` is queued or running, the SSE stream wins and the
 * hook reports `status="uploading"` with a derived `percent`. Otherwise
 * it falls back to the persisted state, returning `status="not_found"`
 * when nothing is known.
 */

import type { UploadResponse } from "@/api/generated/schemas";
import { useUpload } from "@/hooks/use-api";
import { useJobs } from "@/hooks/use-jobs-stream";

export type UploadStatus = UploadResponse["status"];

export interface UploadStatusView {
  status: UploadStatus;
  /** 0–100 while uploading via the live job stream; null otherwise. */
  percent: number | null;
  error: string | null;
}

export function useUploadStatus(folderPath: string | null): UploadStatusView {
  const { data: persisted } = useUpload(folderPath);
  const jobs = useJobs();

  const folderName = folderPath ? (folderPath.split("/").pop() ?? folderPath) : null;
  const activeJob = folderName
    ? jobs.find(
        (j) => j.type === "upload" && j.folder === folderName && (j.status === "queued" || j.status === "running"),
      )
    : undefined;

  if (activeJob) {
    const { current, total } = activeJob.progress;
    const percent = total > 0 ? Math.min(100, Math.floor((current / total) * 100)) : 0;
    return { status: "uploading", percent, error: null };
  }

  if (persisted) {
    return {
      status: persisted.status as UploadStatus,
      percent: null,
      error: persisted.error,
    };
  }

  return { status: "not_found", percent: null, error: null };
}
