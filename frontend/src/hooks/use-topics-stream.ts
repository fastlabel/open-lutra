/**
 * SSE stream connection and writes into the TanStack Query cache.
 * Should be invoked once near the app root.
 */

import { skipToken, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import type { TopicInfo } from "@/api/generated/schemas";

/** SSE log entry (delivered over SSE, so excluded from orval generation). */
export interface LogEntry {
  id: number;
  timestamp: number;
  severity: "info" | "warning" | "danger";
  message: string;
  topic: string | null;
  source: string | null;
}

import { sseKeys } from "@/lib/query-keys";
import { upsertTopicStats } from "@/lib/topic-stats";
import { useQualityHistoryStore } from "@/stores/quality-history-store";

/** SSE connection status. */
export type SseConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected";

/**
 * Connect to the SSE stream and write incoming events into the TanStack Query cache.
 * Should be invoked once near the app root.
 *
 * @param enabled - When false, closes the SSE connection (to reduce load during recording).
 */
export function useTopicsStream(enabled = true) {
  const queryClient = useQueryClient();

  // Pause / resume backend monitoring in lockstep with SSE disconnect.
  useEffect(() => {
    fetch(`/api/topics/${enabled ? "resume" : "pause"}`, { method: "POST" }).catch(() => {});
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    const es = new EventSource("/api/topics/stream");
    const setStatus = (status: SseConnectionStatus) => queryClient.setQueryData(sseKeys.connectionStatus(), status);

    setStatus("connecting");

    // The first topic_stats after a (re)connect carries every row (the server
    // diffs against an empty per-connection state) and must replace the list:
    // after a backend restart, merging would leave rows from the server's
    // previous life frozen in the UI. Later events carry only changed rows.
    let replaceNext = true;

    es.onopen = () => {
      replaceNext = true;
      setStatus("connected");
    };

    es.addEventListener("topic_stats", (e) => {
      const changed: TopicInfo[] = JSON.parse(e.data);
      const next = queryClient.setQueryData<TopicInfo[]>(sseKeys.topicStats(), (old) =>
        replaceNext ? changed : upsertTopicStats(old ?? [], changed),
      );
      replaceNext = false;
      // The quality history advances every tick, even when no row changed.
      useQualityHistoryStore.getState().push(next ?? []);
    });

    es.addEventListener("log", (e) => {
      const log: LogEntry = { ...JSON.parse(e.data), source: "api" };
      queryClient.setQueryData<LogEntry[]>(sseKeys.logs(), (old) => [...(old ?? []), log].slice(-500));
    });

    es.onerror = () => {
      setStatus("reconnecting");
      console.warn("SSE connection lost. Reconnecting...");
    };

    return () => {
      es.close();
      setStatus("disconnected");
    };
  }, [queryClient, enabled]);
}

/**
 * Reactively read topic stats from the SSE cache.
 * useQuery subscribes to the cache key, so components re-render
 * whenever new data is written via setQueryData.
 */
export function useTopicStats(): TopicInfo[] {
  return (
    useQuery<TopicInfo[]>({
      queryKey: sseKeys.topicStats(),
      queryFn: skipToken,
    }).data ?? []
  );
}

/** Reactively read logs from the SSE cache. */
export function useLogs(): LogEntry[] {
  return (
    useQuery<LogEntry[]>({
      queryKey: sseKeys.logs(),
      queryFn: skipToken,
    }).data ?? []
  );
}

/** Hook for appending a log entry from the frontend. */
export function useAddLog() {
  const queryClient = useQueryClient();
  return (severity: "info" | "warning" | "danger", message: string) => {
    const entry: LogEntry = {
      id: -Date.now(),
      timestamp: Date.now() / 1000,
      severity,
      message,
      topic: null,
      source: "ui",
    };
    queryClient.setQueryData<LogEntry[]>(sseKeys.logs(), (old) => [...(old ?? []), entry].slice(-500));
  };
}

/** Reactively read the SSE connection status. */
export function useConnectionStatus(): SseConnectionStatus {
  return (
    useQuery<SseConnectionStatus>({
      queryKey: sseKeys.connectionStatus(),
      queryFn: skipToken,
    }).data ?? "disconnected"
  );
}
