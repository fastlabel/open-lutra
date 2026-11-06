import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  useConfig,
  useFiles,
  useIsRecording,
  useMemory,
  useRecordingStatus,
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

describe("useFiles", () => {
  const before = { started_after: "2026-11-06T00:00:00+09:00", started_before: "2026-11-07T00:00:00+09:00" };
  const after = { started_after: "2026-11-07T00:00:00+09:00", started_before: "2026-11-08T00:00:00+09:00" };
  const files = { output_dir: "/out", entries: [] };

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderWithChangingParams(options?: { keepPreviousWhileLoading?: boolean }) {
    // The second range never resolves, so the hook stays in its loading state after the switch.
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise(() => {}));
    const { wrapper, queryClient } = createWrapper();
    queryClient.setQueryData(["/api/recordings", before], { data: files, status: 200 });
    const hook = renderHook(({ params }) => useFiles(params, options), {
      wrapper,
      initialProps: { params: before },
    });
    hook.rerender({ params: after });
    return hook;
  }

  it("keeps the previous list while a changed filter loads when asked to", () => {
    const { result } = renderWithChangingParams({ keepPreviousWhileLoading: true });
    expect(result.current.data).toEqual(files);
    expect(result.current.isPlaceholderData).toBe(true);
  });

  it("does not keep the previous list by default", () => {
    const { result } = renderWithChangingParams();
    expect(result.current.data).toBeUndefined();
  });
});
