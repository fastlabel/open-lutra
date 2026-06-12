/**
 * API hooks (wrappers around orval-generated hooks).
 *
 * Conventions:
 * - Types are imported directly from `@/api/generated/schemas` (not re-exported here).
 * - Hooks / query-key factories are imported directly from `@/api/generated/{tag}/{tag}`.
 * - A wrapper is only provided when custom logic (refetchInterval, select, enabled, etc.) is needed.
 * - Every hook uses `select` to unwrap the response envelope (`{ data, status, headers }`) and return the data portion.
 *
 * Lifecycle order: initialization → continuous polling → mutations → on-demand queries.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getGetQualityQueryKey,
  getGetTimelineQueryKey,
  useGetQuality,
  useStartQualityAnalysis as useStartQualityAnalysisGenerated,
  useStartTimelineAnalysis as useStartTimelineAnalysisGenerated,
} from "@/api/generated/analysis/analysis";
import { useGetConfig, useGetMemory } from "@/api/generated/config/config";
import {
  getGetVideoStatusQueryKey,
  useStartVideoGeneration as useStartVideoGenerationGenerated,
} from "@/api/generated/media/media";
import { useGetRecordingStatus } from "@/api/generated/recording/recording";
import {
  getGetRecordingsQueryKey,
  useDeleteRecordings as useDeleteRecordingsGenerated,
  useGetRecordings,
  useGetRecordingTaskNames,
  useRenameRecording as useRenameRecordingGenerated,
  useUpdateRecordingMeta as useUpdateRecordingMetaGenerated,
} from "@/api/generated/recordings/recordings";
import type {
  ConfigResponse,
  FilesResponse,
  LatestMessageResponse,
  MemoryInfo,
  QualityResponse,
  RecordingStatus,
  TaskNamesResponse,
  TopicsResponse,
  UploadResponse,
  ValidationResponse,
} from "@/api/generated/schemas";
import {
  useGetTopicMessage,
  useGetTopics,
  useUpdateSubscriptions as useUpdateSubscriptionsGenerated,
} from "@/api/generated/topics/topics";
import {
  getGetUploadQueryKey,
  useGetUpload,
  useStartUpload as useStartUploadGenerated,
} from "@/api/generated/upload/upload";
import {
  getGetValidationQueryKey,
  useGetValidation,
  useStartValidation as useStartValidationGenerated,
} from "@/api/generated/validation/validation";

// ============================================================
// Initialization queries (fetched once on app start)
// ============================================================

/** Fetch application configuration once on first load (cached thereafter). */
export function useConfig() {
  return useGetConfig<ConfigResponse>({
    query: {
      staleTime: Infinity,
      select: (resp) => resp.data as ConfigResponse,
    },
  });
}

// ============================================================
// Continuous polling queries
// ============================================================

/** Poll the recording status every second. */
export function useRecordingStatus() {
  return useGetRecordingStatus<RecordingStatus>({
    query: {
      refetchInterval: 1000,
      select: (resp) => resp.data as RecordingStatus,
    },
  });
}

/** Return only whether recording is in progress (derived from cache via `select`). */
export function useIsRecording(): boolean {
  return (
    useGetRecordingStatus<boolean>({
      query: {
        refetchInterval: 1000,
        select: (resp) => (resp.data as RecordingStatus).is_recording,
      },
    }).data ?? false
  );
}

/** Poll the topic list every 5 seconds (SSE fallback). */
export function useTopics() {
  return useGetTopics<TopicsResponse>({
    query: {
      refetchInterval: 5000,
      select: (resp) => resp.data as TopicsResponse,
    },
  });
}

/** Fetch backend memory usage every 5 seconds. */
export function useMemory() {
  return useGetMemory<MemoryInfo>({
    query: {
      refetchInterval: 5000,
      select: (resp) => resp.data as MemoryInfo,
    },
  });
}

// ============================================================
// Mutations
// ============================================================

/** Mutation that resets the baseline Hz and quality metrics for all topics. */
export function useResetBaseline() {
  return useMutation({
    mutationFn: () => fetch("/api/topics/reset-baseline", { method: "POST" }),
  });
}

/** Mutation that updates the topic subscription list. */
export function useUpdateSubscriptions() {
  return useUpdateSubscriptionsGenerated();
}

/** Mutation that renames a recording folder. */
export function useRenameRecording() {
  const queryClient = useQueryClient();
  return useRenameRecordingGenerated({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getGetRecordingsQueryKey() });
      },
    },
  });
}

/** Mutation that bulk-deletes recording folders. */
export function useDeleteRecordings() {
  const queryClient = useQueryClient();
  return useDeleteRecordingsGenerated({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getGetRecordingsQueryKey() });
      },
    },
  });
}

/** Mutation that updates a recording's task_name / tags. */
export function useUpdateRecordingMeta() {
  const queryClient = useQueryClient();
  return useUpdateRecordingMetaGenerated({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getGetRecordingsQueryKey() });
      },
    },
  });
}

// ============================================================
// On-demand queries (used by specific screens / actions)
// ============================================================

/** Fetch the list of recording folders directly under the output directory. */
export function useFiles() {
  return useGetRecordings<FilesResponse>({
    query: {
      select: (resp) => resp.data as FilesResponse,
    },
  });
}

/** task_name suggestions collected from past recordings, ordered most-recently-used first.
 *
 * Pass `enabled` to fetch only while the autocomplete is open.
 */
export function useTaskNames(options?: { enabled?: boolean }): string[] {
  const result = useGetRecordingTaskNames<TaskNamesResponse>({
    query: {
      enabled: options?.enabled ?? true,
      select: (resp) => resp.data as TaskNamesResponse,
    },
  });
  return result.data?.task_names ?? [];
}

/** Fetch the MCAP quality report (no side effects).
 *
 * Trigger an analysis run via useStartQualityAnalysis().
 */
export function useQualityReport(folderPath: string | null) {
  return useGetQuality<QualityResponse>(
    { path: folderPath ?? "" },
    {
      query: {
        enabled: !!folderPath,
        select: (resp) => resp.data as QualityResponse,
        refetchInterval: (query) => {
          const raw = query.state.data?.data;
          const status = raw && "status" in raw ? raw.status : undefined;
          return status === "analyzing" ? 2000 : false;
        },
      },
    },
  );
}

/** Mutation that starts quality analysis (idempotent).
 *
 * The POST response has the same shape as GET /api/analysis/quality, so write it back to the
 * GET cache in onSuccess (using setQueryData rather than invalidate). This avoids a refetch
 * race that would re-trigger the caller's useEffect.
 */
export function useStartQualityAnalysis() {
  const queryClient = useQueryClient();
  return useStartQualityAnalysisGenerated({
    mutation: {
      onSuccess: (data, variables) => {
        queryClient.setQueryData(getGetQualityQueryKey({ path: variables.params.path }), data);
      },
    },
  });
}

/** Mutation that starts timeline analysis (idempotent).
 *
 * The POST response has the same shape as GET /api/analysis/timeline, so write it back to the
 * GET cache in onSuccess to avoid a refetch race that would re-trigger the caller's useEffect.
 */
export function useStartTimelineAnalysis() {
  const queryClient = useQueryClient();
  return useStartTimelineAnalysisGenerated({
    mutation: {
      onSuccess: (data, variables) => {
        queryClient.setQueryData(getGetTimelineQueryKey({ path: variables.params.path }), data);
      },
    },
  });
}

/** Fetch the cached validation report for a recording (no side effects).
 *
 * Trigger a run via useStartValidation(). Polls every 2s while the backend
 * reports `status === "analyzing"`, mirroring useQualityReport().
 */
export function useValidation(folderPath: string | null) {
  return useGetValidation<ValidationResponse>(
    { path: folderPath ?? "" },
    {
      query: {
        enabled: !!folderPath,
        select: (resp) => resp.data as ValidationResponse,
        refetchInterval: (query) => {
          const raw = query.state.data?.data;
          const status = raw && "status" in raw ? raw.status : undefined;
          return status === "analyzing" ? 2000 : false;
        },
      },
    },
  );
}

/** Start a validation run (idempotent).
 *
 * POST returns the same envelope as GET /api/validation, so write the response
 * back into the GET cache to avoid a refetch race that would re-trigger
 * caller-side useEffect chains.
 */
export function useStartValidation() {
  const queryClient = useQueryClient();
  return useStartValidationGenerated({
    mutation: {
      onSuccess: (data, variables) => {
        queryClient.setQueryData(getGetValidationQueryKey({ path: variables.params.path }), data);
      },
    },
  });
}

/** Fetch the persisted upload state for a recording (no side effects).
 *
 * Trigger an upload via useStartUpload(). Polls every 2s while the backend
 * reports `status === "uploading"` as a safety net for any SSE event drops;
 * the SSE job stream is the primary live-progress source.
 */
export function useUpload(folderPath: string | null) {
  return useGetUpload<UploadResponse>(
    { path: folderPath ?? "" },
    {
      query: {
        enabled: !!folderPath,
        select: (resp) => resp.data as UploadResponse,
        refetchInterval: (query) => {
          const raw = query.state.data?.data;
          const status = raw && "status" in raw ? raw.status : undefined;
          return status === "uploading" ? 2000 : false;
        },
      },
    },
  );
}

/** Start an upload (idempotent; always overwrites per issue #6).
 *
 * POST returns the same envelope as GET /api/upload, so write the response back
 * into the GET cache to avoid a refetch race.
 */
export function useStartUpload() {
  const queryClient = useQueryClient();
  return useStartUploadGenerated({
    mutation: {
      onSuccess: (data, variables) => {
        queryClient.setQueryData(getGetUploadQueryKey({ path: variables.params.path }), data);
      },
    },
  });
}

/** Mutation that starts MP4 video generation (idempotent).
 *
 * The POST response has the same envelope shape as GET /api/media/video
 * (`{ data: VideoResponse }`), so write it back to the GET cache in onSuccess. `videoData.status`
 * flips immediately to `generating`/`ready`, preventing the preview-panel useEffect from looping
 * on the `not_generated` state.
 */
export function useStartVideoGeneration() {
  const queryClient = useQueryClient();
  return useStartVideoGenerationGenerated({
    mutation: {
      onSuccess: (data, variables) => {
        queryClient.setQueryData(getGetVideoStatusQueryKey({ path: variables.params.path }), data);
      },
    },
  });
}

/** Fetch the latest message for a given topic.
 *
 * The backend uses on-demand capture: the first call returns `message=null` (it sets a flag and
 * populates the real data on the next receive). `null` means "not yet received", so callers
 * should branch into a "waiting" display.
 */
export function useTopicMessage(topicName: string | null) {
  return useGetTopicMessage<Record<string, unknown> | null>(
    { topic: topicName ?? "" },
    {
      query: {
        enabled: !!topicName,
        refetchInterval: 2000,
        select: (resp) => (resp.data as LatestMessageResponse).message,
      },
    },
  );
}
