import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// --- Mock setup ---

const {
  mockSetState,
  mockAddMarker,
  mockStartRecordingApi,
  mockStopRecordingApi,
  mockGetFiles,
  mockToast,
  mockSoundEnabled,
  mockPlayStart,
  mockPlayStop,
} = vi.hoisted(() => {
  const mockAddMarker = vi.fn();
  return {
    mockSetState: vi.fn(),
    mockAddMarker,
    mockStartRecordingApi: vi.fn(() => Promise.resolve({ status: 200, data: {} })),
    mockStopRecordingApi: vi.fn(() =>
      Promise.resolve({ status: 200, data: { duration_sec: 10.5, output_path: "/data/test.mcap" } }),
    ),
    mockGetFiles: vi.fn(),
    mockToast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
    mockSoundEnabled: { current: true },
    mockPlayStart: vi.fn(),
    mockPlayStop: vi.fn(),
  };
});

vi.mock("@/lib/query-client", async () => {
  const { QueryClient: QC } = await import("@tanstack/react-query");
  return {
    queryClient: new QC({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    }),
  };
});

vi.mock("@/api/generated/recording/recording", () => ({
  startRecording: mockStartRecordingApi,
  stopRecording: mockStopRecordingApi,
  getGetRecordingStatusQueryKey: vi.fn(() => ["recording-status"]),
}));

vi.mock("@/api/generated/recordings/recordings", () => ({
  getRecordings: mockGetFiles,
  getGetRecordingsQueryKey: vi.fn(() => ["recordings"]),
}));

vi.mock("@/api/generated/analysis/analysis", () => ({
  getGetQualityQueryKey: vi.fn((params: { path: string }) => ["quality", params.path]),
}));

vi.mock("../store", () => ({
  useRecordingStore: {
    setState: mockSetState,
    getState: vi.fn(() => ({ soundEnabled: mockSoundEnabled.current })),
  },
}));

vi.mock("../sounds", () => ({
  playStart: mockPlayStart,
  playStop: mockPlayStop,
  playTick: vi.fn(),
  unlock: vi.fn(),
}));

vi.mock("@/stores/quality-history-store", () => ({
  useQualityHistoryStore: {
    getState: vi.fn(() => ({
      addMarker: mockAddMarker,
    })),
  },
}));

vi.mock("@/features/settings", () => ({
  useSettingsStore: {
    getState: vi.fn(() => ({ taskName: "test-task", metadata: {} })),
  },
}));

vi.mock("@/lib/query-keys", () => ({
  sseKeys: {
    logs: vi.fn(() => ["sse-logs"]),
  },
}));

vi.mock("@/stores/toast-store", () => ({
  toast: mockToast,
}));

import { getGetConfigQueryKey } from "@/api/generated/config/config";
import { useSettingsStore } from "@/features/settings";
import { queryClient } from "@/lib/query-client";
import { startRecordingMutation, stopRecordingMutation } from "../mutations";

/** Helper that flushes all pending Promises after mutate. */
async function flushMutation() {
  await vi.advanceTimersByTimeAsync(0);
  // Drain the async chain inside MutationObserver.
  await vi.advanceTimersByTimeAsync(0);
}

/**
 * Helper for MutationObserver error tests.
 * Suppresses the case where Promise rejections inside TanStack Query's
 * MutationObserver.mutate() get caught by vitest's process-level handler.
 */
function suppressUnhandledRejection() {
  // The vitest worker captures via process.on, so hook both.
  const windowHandler = (e: PromiseRejectionEvent) => e.preventDefault();
  const processHandler = () => {};
  window.addEventListener("unhandledrejection", windowHandler);
  process.on("unhandledRejection", processHandler);
  return () => {
    window.removeEventListener("unhandledrejection", windowHandler);
    process.removeListener("unhandledRejection", processHandler);
  };
}

// --- startRecordingMutation ---

describe("startRecordingMutation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockSoundEnabled.current = true;
    mockStartRecordingApi.mockResolvedValue({ status: 200, data: {} });
  });

  afterEach(async () => {
    await flushMutation();
    queryClient.removeQueries({ queryKey: getGetConfigQueryKey() });
    vi.useRealTimers();
  });

  it("mutationFn calls the API with the task name", async () => {
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockStartRecordingApi).toHaveBeenCalledWith({
      topics: ["/topic_a"],
      task_name: "test-task",
      metadata: {},
    });
  });

  it("mutationFn: sends task_name=null when taskName is empty", async () => {
    vi.mocked(useSettingsStore.getState).mockReturnValueOnce({ taskName: "", metadata: {} } as ReturnType<
      typeof useSettingsStore.getState
    >);
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockStartRecordingApi).toHaveBeenCalledWith({
      topics: ["/topic_a"],
      task_name: null,
      metadata: {},
    });
  });

  it("mutationFn: sends the sticky metadata selection", async () => {
    vi.mocked(useSettingsStore.getState).mockReturnValueOnce({
      taskName: "test-task",
      metadata: { operator_id: "op001", target_object: "box" } as Record<string, string>,
    } as ReturnType<typeof useSettingsStore.getState>);
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockStartRecordingApi).toHaveBeenCalledWith({
      topics: ["/topic_a"],
      task_name: "test-task",
      metadata: { operator_id: "op001", target_object: "box" },
    });
  });

  it("mutationFn: drops sticky metadata whose field is not in the active config", async () => {
    // The store still holds a value for `stale_field` (e.g. left over after switching
    // RECORDING_CONFIG); only fields present in the active config should be sent.
    queryClient.setQueryData(getGetConfigQueryKey(), {
      data: {
        metadata_fields: [
          { key: "operator_id", label: "Operator ID", type: "number", pattern: null, placeholder: null, options: [] },
        ],
      },
    });
    vi.mocked(useSettingsStore.getState).mockReturnValueOnce({
      taskName: "test-task",
      metadata: { operator_id: "op001", stale_field: "x" } as Record<string, string>,
    } as ReturnType<typeof useSettingsStore.getState>);
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockStartRecordingApi).toHaveBeenCalledWith({
      topics: ["/topic_a"],
      task_name: "test-task",
      metadata: { operator_id: "op001" },
    });
  });

  it("sets isStarting=true on mutate", async () => {
    startRecordingMutation.mutate(["/topic_a"]);
    expect(mockSetState).toHaveBeenCalledWith({ isStarting: true });
    await flushMutation();
  });

  it("adds a marker on success", async () => {
    startRecordingMutation.mutate(["/topic_a", "/topic_b"]);
    await flushMutation();

    expect(mockAddMarker).toHaveBeenCalledWith("start");
  });

  it("shows the start notification toast on success", async () => {
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockToast.success).toHaveBeenCalledWith("Recording started");
  });

  it("plays the start chime on success", async () => {
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockPlayStart).toHaveBeenCalledTimes(1);
  });

  it("does not play the start chime when sound is disabled", async () => {
    mockSoundEnabled.current = false;
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockPlayStart).not.toHaveBeenCalled();
  });

  it("onSuccess: invalidates the file list 500ms later", async () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    invalidateSpy.mockClear();
    await vi.advanceTimersByTimeAsync(500);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["recordings"] });
  });

  it("sets isStarting=false on settled", async () => {
    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockSetState).toHaveBeenCalledWith({ isStarting: false });
  });

  it("shows an error toast on error", async () => {
    const cleanup = suppressUnhandledRejection();
    mockStartRecordingApi.mockRejectedValueOnce(new Error("Connection error"));

    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockToast.error).toHaveBeenCalledWith("Connection error");
    cleanup();
  });

  it("uses the default message when error.message is empty", async () => {
    const cleanup = suppressUnhandledRejection();
    mockStartRecordingApi.mockRejectedValueOnce(new Error(""));

    startRecordingMutation.mutate(["/topic_a"]);
    await flushMutation();

    expect(mockToast.error).toHaveBeenCalledWith("Failed to start recording");
    cleanup();
  });
});

// --- stopRecordingMutation ---

describe("stopRecordingMutation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    mockSoundEnabled.current = true;
    // The useSettingsStore mock persists mockReturnValue across tests, so reset to default each time.
    vi.mocked(useSettingsStore.getState).mockReturnValue({ taskName: "test-task", metadata: {} } as ReturnType<
      typeof useSettingsStore.getState
    >);
    mockStopRecordingApi.mockResolvedValue({
      status: 200,
      data: { duration_sec: 10.5, output_path: "/data/test.mcap" },
    });
    // Default fetchQuery mock (called inside onSuccess).
    vi.spyOn(queryClient, "fetchQuery").mockResolvedValue({
      data: { entries: [] },
    });
  });

  afterEach(async () => {
    await flushMutation();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("sets isStopping=true on mutate", async () => {
    stopRecordingMutation.mutate(undefined);
    expect(mockSetState).toHaveBeenCalledWith({ isStopping: true });
    await flushMutation();
  });

  it("adds a marker and saves completion info to the store on success", async () => {
    vi.spyOn(queryClient, "getQueryData").mockReturnValue({
      data: {
        entries: [
          {
            name: "rec_001",
            path: "/data/rec_001",
            size: 2048,
            modified_at: 0,
            topic_count: 3,
            recording_start_ns: null,
            duration_ns: null,
            message_count: 500,
            has_quality_report: false,
          },
        ],
      },
    });

    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    expect(mockAddMarker).toHaveBeenCalledWith("stop");
    expect(mockSetState).toHaveBeenCalledWith(
      expect.objectContaining({
        finishedRecording: expect.objectContaining({
          name: "rec_001",
          path: "/data/rec_001",
          durationSec: 10.5,
          messageCount: 500,
          topicCount: 3,
          size: 2048,
        }),
      }),
    );
  });

  it("onSuccess: synthesizes from the response and saves when entries is empty", async () => {
    vi.spyOn(queryClient, "getQueryData").mockReturnValue({ data: { entries: [] } });

    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    expect(mockSetState).toHaveBeenCalledWith(
      expect.objectContaining({
        finishedRecording: expect.objectContaining({
          name: "test.mcap",
          path: "/data/test.mcap",
          durationSec: 10.5,
          messageCount: null,
          topicCount: null,
          size: 0,
        }),
      }),
    );
  });

  it("onSuccess (status!==200): does not save finishedRecording", async () => {
    mockStopRecordingApi.mockResolvedValueOnce({ status: 500, data: { duration_sec: 0, output_path: "" } });
    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    const finishedCalls = mockSetState.mock.calls.filter((call) => {
      const arg = call[0] as { finishedRecording?: unknown };
      return arg.finishedRecording !== undefined;
    });
    expect(finishedCalls).toHaveLength(0);
  });

  it("plays the stop chime on success", async () => {
    vi.spyOn(queryClient, "getQueryData").mockReturnValue({ data: { entries: [] } });
    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    expect(mockPlayStop).toHaveBeenCalledTimes(1);
  });

  it("does not play the stop chime when status!==200", async () => {
    mockStopRecordingApi.mockResolvedValueOnce({ status: 500, data: { duration_sec: 0, output_path: "" } });
    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    expect(mockPlayStop).not.toHaveBeenCalled();
  });

  it("does not play the stop chime when sound is disabled", async () => {
    mockSoundEnabled.current = false;
    vi.spyOn(queryClient, "getQueryData").mockReturnValue({ data: { entries: [] } });
    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    expect(mockPlayStop).not.toHaveBeenCalled();
  });

  it("invalidates the quality query in stages", async () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries").mockResolvedValue(undefined);
    vi.spyOn(queryClient, "getQueryData").mockReturnValue({
      data: {
        entries: [{ name: "rec_001", path: "/data/rec_001" }],
      },
    });

    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    // Drain each setTimeout (1000, 4000, 10000, 20000, 40000ms) in order and verify the invalidate call each time.
    const delaysMs = [1000, 4000, 10000, 20000, 40000];
    let expectedQualityCalls = 0;
    for (const delayMs of delaysMs) {
      invalidateSpy.mockClear();
      await vi.advanceTimersByTimeAsync(delayMs);
      expectedQualityCalls = 1;
      expect(invalidateSpy).toHaveBeenCalledTimes(expectedQualityCalls);
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["quality", "/data/rec_001"] });
    }
  });

  it("sets isStopping=false on settled", async () => {
    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    expect(mockSetState).toHaveBeenCalledWith({ isStopping: false });
  });

  it("shows an error toast on error", async () => {
    const cleanup = suppressUnhandledRejection();
    mockStopRecordingApi.mockRejectedValueOnce(new Error("Stop failed"));

    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    expect(mockToast.error).toHaveBeenCalledWith("Stop failed");
    cleanup();
  });

  it("uses the default message when error.message is empty", async () => {
    const cleanup = suppressUnhandledRejection();
    mockStopRecordingApi.mockRejectedValueOnce(new Error(""));

    stopRecordingMutation.mutate(undefined);
    await flushMutation();

    expect(mockToast.error).toHaveBeenCalledWith("Failed to stop recording");
    cleanup();
  });
});
