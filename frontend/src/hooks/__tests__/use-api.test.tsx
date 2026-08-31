import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import {
  useConfig,
  useIsRecording,
  useMemory,
  useRecordingStatus,
  useStorage,
  useTaskNames,
  useTopics,
  useValidation,
} from "../use-api";

/** Create a QueryClientProvider wrapper for tests. */
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
    },
  });
  return {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
    queryClient,
  };
}

// orval-generated query keys use the API path as-is.
const QUERY_KEYS = {
  config: ["/api/config"],
  recordingStatus: ["/api/recording/status"],
  topics: ["/api/topics"],
  memory: ["/api/system/memory"],
  storage: ["/api/system/storage"],
  taskNames: ["/api/recordings/task-names"],
  validation: (path: string) => ["/api/validation", { path }] as const,
} as const;

describe("useConfig", () => {
  it("unwraps data from the response envelope via select", async () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(QUERY_KEYS.config, {
      data: { output_dir: "/data", default_topics: ["/topic"] },
      status: 200,
    });

    const { result } = renderHook(() => useConfig(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data).toEqual({
      output_dir: "/data",
      default_topics: ["/topic"],
    });
  });
});

describe("useRecordingStatus", () => {
  it("unwraps RecordingStatus via select", async () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(QUERY_KEYS.recordingStatus, {
      data: { is_recording: true, elapsed_sec: 42.5, output_dir: "/data" },
      status: 200,
    });

    const { result } = renderHook(() => useRecordingStatus(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.is_recording).toBe(true);
    expect(result.current.data?.elapsed_sec).toBe(42.5);
  });
});

describe("useIsRecording", () => {
  it("returns true while recording", async () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(QUERY_KEYS.recordingStatus, {
      data: { is_recording: true, elapsed_sec: 0 },
      status: 200,
    });

    const { result } = renderHook(() => useIsRecording(), { wrapper });

    await waitFor(() => expect(result.current).toBe(true));
  });

  it("returns false when not recording", async () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(QUERY_KEYS.recordingStatus, {
      data: { is_recording: false, elapsed_sec: 0 },
      status: 200,
    });

    const { result } = renderHook(() => useIsRecording(), { wrapper });

    await waitFor(() => expect(result.current).toBe(false));
  });

  it("returns false when no data has been fetched", () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useIsRecording(), { wrapper });

    expect(result.current).toBe(false);
  });
});

describe("useTopics", () => {
  it("unwraps TopicsResponse via select", async () => {
    const { wrapper, queryClient } = createWrapper();
    const topicsData = {
      topics: [{ name: "/joint_states", msg_type: "sensor_msgs/msg/JointState" }],
    };
    queryClient.setQueryData(QUERY_KEYS.topics, {
      data: topicsData,
      status: 200,
    });

    const { result } = renderHook(() => useTopics(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.topics).toHaveLength(1);
    expect(result.current.data?.topics[0].name).toBe("/joint_states");
  });
});

describe("useMemory", () => {
  it("unwraps MemoryInfo via select", async () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(QUERY_KEYS.memory, {
      data: { used_bytes: 512, limit_bytes: 1024 },
      status: 200,
    });

    const { result } = renderHook(() => useMemory(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.used_bytes).toBe(512);
    expect(result.current.data?.limit_bytes).toBe(1024);
  });
});

describe("useStorage", () => {
  it("unwraps StorageInfo via select", async () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(QUERY_KEYS.storage, {
      data: { path: "/data/output", free_bytes: 1900 },
      status: 200,
    });

    const { result } = renderHook(() => useStorage(), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.free_bytes).toBe(1900);
    expect(result.current.data?.path).toBe("/data/output");
  });
});

describe("useTaskNames", () => {
  it("unwraps task_names from the response envelope", async () => {
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(QUERY_KEYS.taskNames, {
      data: { task_names: ["pick", "place"] },
      status: 200,
    });

    const { result } = renderHook(() => useTaskNames(), { wrapper });

    await waitFor(() => expect(result.current.length).toBeGreaterThan(0));
    expect(result.current).toEqual(["pick", "place"]);
  });

  it("returns an empty array when no data has been fetched", () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useTaskNames({ enabled: false }), { wrapper });
    expect(result.current).toEqual([]);
  });
});

describe("useValidation", () => {
  it("unwraps the data portion of ValidationResponse via select", async () => {
    const { wrapper, queryClient } = createWrapper();
    const payload = {
      status: "ready",
      report: {
        overall_status: "warn",
        results: [],
        task_name: "pick",
        executed_at: "2026-05-25T00:00:00",
      },
      error: null,
    };
    queryClient.setQueryData(QUERY_KEYS.validation("rec_001"), { data: payload, status: 200 });

    const { result } = renderHook(() => useValidation("rec_001"), { wrapper });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.status).toBe("ready");
    expect(result.current.data?.report?.overall_status).toBe("warn");
  });

  it("does not fetch when folderPath is null (enabled=false)", () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useValidation(null), { wrapper });
    // enabled=false, so status stays pending and data is undefined.
    expect(result.current.data).toBeUndefined();
    expect(result.current.fetchStatus).toBe("idle");
  });
});
