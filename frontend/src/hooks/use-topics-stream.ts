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
import { mergeTopicStatsDelta, type TopicStatsDelta } from "@/lib/topic-stats-delta";
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

    es.onopen = () => setStatus("connected");

    // Full snapshot (on connect + periodically): replace the whole list.
    es.addEventListener("topic_stats", (e) => {
      const data: TopicInfo[] = JSON.parse(e.data);
      queryClient.setQueryData(sseKeys.topicStats(), data);
      // Accumulate quality time-series data.
      useQualityHistoryStore.getState().push(data);
    });

    // Per-tick delta: merge changed/removed rows into the cached list.
    es.addEventListener("topic_stats_delta", (e) => {
      const delta: TopicStatsDelta = JSON.parse(e.data);
      const merged = mergeTopicStatsDelta(queryClient.getQueryData<TopicInfo[]>(sseKeys.topicStats()) ?? [], delta);
      queryClient.setQueryData(sseKeys.topicStats(), merged);
      // The quality history advances every tick, even when no row changed.
      useQualityHistoryStore.getState().push(merged);
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
