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
import { useEffect, useRef } from "react";
import { getGetQualityQueryKey, getGetTimelineQueryKey } from "@/api/generated/analysis/analysis";
import { getGetJointsQueryKey, getGetVideoStatusQueryKey } from "@/api/generated/media/media";
import { getGetRecordingsQueryKey } from "@/api/generated/recordings/recordings";
import type { JobSchema } from "@/api/generated/schemas";
import { getGetValidationQueryKey } from "@/api/generated/validation/validation";
import { useAddLog } from "@/hooks/use-topics-stream";
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
};

/**
 * Open the SSE connection and synchronize job state into the cache.
 * Should be invoked once near the app root.
 */
export function useJobsStream() {
  const queryClient = useQueryClient();
  // `useAddLog` returns a fresh function each render; keep it in a ref so the
  // SSE effect (keyed on queryClient) doesn't reconnect on every render.
  const addLog = useAddLog();
  const addLogRef = useRef(addLog);
  addLogRef.current = addLog;

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
        // LeRobot export has no view to refresh, so surface its async result as a log
        // (the only feedback besides the in-flight StatusBar pill).
        if (job.type === "lerobot_export") {
          if (evt === "job_completed") {
            addLogRef.current("info", `LeRobot export completed: _lerobot_exports/${job.folder}/`);
          } else {
            addLogRef.current("danger", `LeRobot export failed (${job.folder}): ${job.error ?? "unknown error"}`);
          }
        }
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
