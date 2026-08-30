/**
 * Subscription hook for the job-queue SSE stream.
 *
 * Receives state-change events from `/api/jobs/stream` and updates the TanStack Query cache
 * (`sseKeys.jobs()`). Both the preview panel and the footer (Phase 1) subscribe to the same
 * cache.
 *
 * Design:
 * - The `queue_snapshot` event on connect replaces the full job list.
 * - `job_added` / `job_started` / `job_progress` / `job_completed` / `job_failed` upsert
 *   individual jobs.
 * - On `job_completed` / `job_failed`, related queries are invalidated based on job type to
 *   refresh associated views (quality report, timeline, etc.).
 */

import { skipToken, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { getGetQualityQueryKey, getGetTimelineQueryKey } from "@/api/generated/analysis/analysis";
import { getGetStorageQueryKey } from "@/api/generated/config/config";
import { getGetJointsQueryKey, getGetVideoStatusQueryKey } from "@/api/generated/media/media";
import { getGetRecordingsQueryKey } from "@/api/generated/recordings/recordings";
import type { JobSchema } from "@/api/generated/schemas";
import { getGetUploadQueryKey } from "@/api/generated/upload/upload";
import { getGetValidationQueryKey } from "@/api/generated/validation/validation";
import { sseKeys } from "@/lib/query-keys";

/**
 * Map of query-key prefixes to invalidate on job completion.
 *
 * orval-generated query keys have the shape `[<url>, { <params> }]`. Calling the key factory
 * without params returns `[<url>]`, so invalidating by that prefix matches every query for
 * the same endpoint (also re-fetching caches for other folders that use different params).
 * To avoid hardcoding URL strings, the orval-generated key factories are used directly.
 */
const JOB_COMPLETION_INVALIDATIONS: Record<string, readonly (readonly unknown[])[]> = {
  quality: [getGetQualityQueryKey()],
  timeline: [getGetTimelineQueryKey()],
  media: [getGetVideoStatusQueryKey(), getGetJointsQueryKey()],
  // Validation completion also flips `validation_overall_status` on FileEntry,
  // so refresh the recordings list to update the inline row badge.
  validation: [getGetValidationQueryKey(), getGetRecordingsQueryKey()],
  // Upload completion flips `upload_status` on FileEntry; refresh the list so
  // the inline row badge picks up the new state.
  upload: [getGetUploadQueryKey(), getGetRecordingsQueryKey()],
};

/**
 * Open the SSE connection and synchronize job state into the cache.
 * Should be invoked once near the app root.
 */
export function useJobsStream() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const es = new EventSource("/api/jobs/stream");

    const upsert = (job: JobSchema) => {
      queryClient.setQueryData<JobSchema[]>(sseKeys.jobs(), (old) => {
        const list = old ?? [];
        const idx = list.findIndex((j) => j.job_id === job.job_id);
        if (idx >= 0) {
          const next = [...list];
          next[idx] = job;
          return next;
        }
        return [job, ...list];
      });
    };

    /** Invalidate related queries when a job completes or fails. */
    const invalidateRelated = (job: JobSchema) => {
      // Every job type writes into the output volume (analysis JSON, MP4, zip,
      // exported dataset), so a finished job is the point at which the recording
      // screen's free-space readout is worth re-reading. Invalidating while that
      // screen is closed costs nothing: the refetch happens when it next mounts.
      queryClient.invalidateQueries({ queryKey: getGetStorageQueryKey() });
      const keys = JOB_COMPLETION_INVALIDATIONS[job.type];
      if (!keys) return;
      for (const queryKey of keys) {
        queryClient.invalidateQueries({ queryKey });
      }
    };

    es.addEventListener("queue_snapshot", (e) => {
      const data = JSON.parse(e.data) as { jobs: JobSchema[] };
      queryClient.setQueryData<JobSchema[]>(sseKeys.jobs(), data.jobs);
    });

    for (const evt of ["job_added", "job_started", "job_progress"] as const) {
      es.addEventListener(evt, (e) => {
        const job = JSON.parse(e.data) as JobSchema;
        upsert(job);
      });
    }

    for (const evt of ["job_completed", "job_failed"] as const) {
      es.addEventListener(evt, (e) => {
        const job = JSON.parse(e.data) as JobSchema;
        upsert(job);
        // Invalidate related REST queries when a job completes or fails.
        // (e.g. quality completes → the quality summary on the MCAP detail page auto-refetches.)
        invalidateRelated(job);
      });
    }

    es.onerror = () => {
      console.warn("Jobs SSE connection lost. Reconnecting...");
    };

    return () => {
      es.close();
    };
  }, [queryClient]);
}

/** Reactively read the current list of jobs. */
export function useJobs(): JobSchema[] {
  return (
    useQuery<JobSchema[]>({
      queryKey: sseKeys.jobs(),
      queryFn: skipToken,
    }).data ?? []
  );
}

/** Fetch the job for a given job_id. Lookup remains available from history after completion/failure. */
export function useJob(jobId: string | null | undefined): JobSchema | undefined {
  const jobs = useJobs();
  if (!jobId) return undefined;
  return jobs.find((j) => j.job_id === jobId);
}

/** Reactively read the active (queued/running) upload job for a single folder.
 *
 * Uses TanStack Query `select` so a subscriber re-renders only when its own
 * folder's upload job changes, not on every job-stream tick. This keeps a long
 * recordings list cheap to render while an upload is in flight.
 */
export function useUploadJob(folderName: string): JobSchema | undefined {
  return useQuery<JobSchema[], Error, JobSchema | undefined>({
    queryKey: sseKeys.jobs(),
    queryFn: skipToken,
    select: (jobs) =>
      jobs.find(
        (j) => j.type === "upload" && j.folder === folderName && (j.status === "queued" || j.status === "running"),
      ),
  }).data;
}
