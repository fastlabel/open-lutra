/** MutationObserver definitions for recording operations.
 *
 * Orchestration layer that lets non-React code (the Zustand store) drive TanStack Query mutations.
 * Handles the API calls, cache invalidation, and coordination across multiple stores.
 */
import { MutationObserver } from "@tanstack/react-query";
import { getGetQualityQueryKey } from "@/api/generated/analysis/analysis";
import { getGetConfigQueryKey } from "@/api/generated/config/config";
import {
  getGetRecordingStatusQueryKey,
  startRecording as startRecordingApi,
  stopRecording as stopRecordingApi,
} from "@/api/generated/recording/recording";
import { getGetRecordingsQueryKey } from "@/api/generated/recordings/recordings";
import type { ConfigResponse, FilesResponse } from "@/api/generated/schemas";
import { useSettingsStore } from "@/features/settings";
import type { LogEntry } from "@/hooks/use-topics-stream";
import { queryClient } from "@/lib/query-client";
import { sseKeys } from "@/lib/query-keys";
import { useQualityHistoryStore } from "@/stores/quality-history-store";
import { toast } from "@/stores/toast-store";
import * as sounds from "./sounds";
import { useRecordingStore } from "./store";

// --- Helpers ---

/** Append a UI log entry to the TanStack Query cache. */
function addLog(severity: "info" | "warning" | "danger", message: string) {
  const entry: LogEntry = {
    id: -Date.now(),
    timestamp: Date.now() / 1000,
    severity,
    message,
    topic: null,
    source: "ui",
  };
  queryClient.setQueryData<LogEntry[]>(sseKeys.logs(), (old) => [...(old ?? []), entry].slice(-500));
}

// --- MutationObserver ---

/** Start-recording mutation. */
export const startRecordingMutation = new MutationObserver(queryClient, {
  mutationFn: (topics: string[]) => {
    const { taskName, metadata } = useSettingsStore.getState();
    // Drop sticky metadata whose field is no longer in the active config (e.g. after
    // switching RECORDING_CONFIG) so orphaned localStorage values are not silently
    // attached to every recording. Falls back to the raw map if config is not cached yet.
    const config = queryClient.getQueryData<{ data: ConfigResponse }>(getGetConfigQueryKey())?.data;
    const activeMetadata = config
      ? Object.fromEntries(
          Object.entries(metadata).filter(([key]) => config.metadata_fields.some((f) => f.key === key)),
        )
      : metadata;
    return startRecordingApi({ topics, task_name: taskName || null, metadata: activeMetadata });
  },
  onMutate: () => {
    useRecordingStore.setState({ isStarting: true });
  },
  onSuccess: (_data, topics) => {
    useQualityHistoryStore.getState().addMarker("start");
    if (useRecordingStore.getState().soundEnabled) sounds.playStart();
    toast.success("Recording started");
    addLog("info", `Recording started (${topics.length} topics)`);
    queryClient.invalidateQueries({ queryKey: getGetRecordingStatusQueryKey() });
    setTimeout(() => queryClient.invalidateQueries({ queryKey: getGetRecordingsQueryKey() }), 500);
  },
  onError: (error) => {
    const msg = error.message || "Failed to start recording";
    toast.error(msg);
    addLog("danger", `Recording start failed: ${msg}`);
  },
  onSettled: () => {
    useRecordingStore.setState({ isStarting: false });
  },
});

/** Stop-recording mutation. */
export const stopRecordingMutation = new MutationObserver(queryClient, {
  mutationFn: () => stopRecordingApi({}),
  onMutate: () => {
    useRecordingStore.setState({ isStopping: true });
  },
  onSuccess: async (resp) => {
    useQualityHistoryStore.getState().addMarker("stop");
    queryClient.invalidateQueries({ queryKey: getGetRecordingStatusQueryKey() });
    if (resp.status !== 200) return;
    const d = resp.data;
    if (useRecordingStore.getState().soundEnabled) sounds.playStop();
    toast.success("Recording completed");
    addLog("info", `Recording stopped (${d.duration_sec.toFixed(1)}s) → ${d.output_path}`);
    // Force-refresh the file list to fetch the latest mcap.
    // invalidateQueries notifies every observer to refetch, ensuring the UI updates.
    // (Cases existed where fetchQuery alone skipped observer re-renders.)
    await queryClient.invalidateQueries({ queryKey: getGetRecordingsQueryKey() });
    const filesResp = queryClient.getQueryData<{ data: FilesResponse }>(getGetRecordingsQueryKey());
    const filesData = filesResp?.data;
    // The first entry is always the newest recording (scan_output_dir returns recording_start_ns descending).
    const firstEntry = filesData?.entries[0];

    // Save the latest recording info to the store for the completion banner (synthesize from the API response if FileEntry is missing).
    if (firstEntry) {
      useRecordingStore.setState({
        finishedRecording: {
          name: firstEntry.name,
          path: firstEntry.path,
          durationSec: d.duration_sec,
          messageCount: firstEntry.message_count,
          topicCount: firstEntry.topic_count,
          size: firstEntry.size,
        },
      });
    } else {
      // Path-only fallback (entries is empty or unfetched). split always returns at least one element, so pop returns a string.
      const name = d.output_path.split("/").pop() as string;
      useRecordingStore.setState({
        finishedRecording: {
          name,
          path: d.output_path,
          durationSec: d.duration_sec,
          messageCount: null,
          topicCount: null,
          size: 0,
        },
      });
    }

    // Progressively invalidate the quality query so the UI reflects the analysis progress.
    // Retry multiple times because the background analysis completion timing varies with recording length.
    if (firstEntry) {
      const qualityKey = getGetQualityQueryKey({ path: firstEntry.path });
      for (const delayMs of [1000, 4000, 10000, 20000, 40000]) {
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: qualityKey });
        }, delayMs);
      }
    }
  },
  onError: (error) => {
    const msg = error.message || "Failed to stop recording";
    toast.error(msg);
    addLog("danger", `Recording stop failed: ${msg}`);
  },
  onSettled: () => {
    useRecordingStore.setState({ isStopping: false });
  },
});
