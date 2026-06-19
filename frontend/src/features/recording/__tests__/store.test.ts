import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// --- Mock setup (initialized via vi.hoisted before vi.mock) ---

const {
  mockMutateStart,
  mockMutateStop,
  mockShowMessage,
  mockClearMessageTimer,
  mockGetQueryData,
  mockSelectedTopics,
} = vi.hoisted(() => ({
  mockMutateStart: vi.fn(),
  mockMutateStop: vi.fn(),
  mockShowMessage: vi.fn(),
  mockClearMessageTimer: vi.fn(),
  mockGetQueryData: vi.fn((_key?: unknown): unknown => undefined),
  mockSelectedTopics: { current: new Set<string>(["/topic_a", "/topic_b"]) },
}));

vi.mock("zustand/middleware", () => ({
  persist: (fn: unknown) => fn,
  devtools: (fn: unknown) => fn,
}));

vi.mock("../mutations", () => ({
  startRecordingMutation: { mutate: mockMutateStart },
  stopRecordingMutation: { mutate: mockMutateStop },
  showMessage: mockShowMessage,
  clearMessageTimer: mockClearMessageTimer,
}));

vi.mock("@/lib/query-client", () => ({
  queryClient: {
    getQueryData: mockGetQueryData,
  },
}));

vi.mock("@/api/generated/recording/recording", () => ({
  getGetRecordingStatusQueryKey: vi.fn(() => ["recording-status"]),
}));

vi.mock("@/features/live-topics", () => ({
  useLiveTopicsStore: {
    getState: vi.fn(() => ({
      selectedTopics: mockSelectedTopics.current,
    })),
  },
}));

import { DELAY_OPTIONS, useRecordingStore } from "../store";

// --- Tests ---

describe("DELAY_OPTIONS", () => {
  it("has options 0, 3, 5, 10", () => {
    expect(DELAY_OPTIONS).toEqual([0, 3, 5, 10]);
  });
});

describe("useRecordingStore", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    // Reset the store to its initial state
    useRecordingStore.setState({
      delaySec: 0,
      stopLiveMonitorDuringRecording: false,
      countdownSec: null,
      isStarting: false,
      isStopping: false,
      message: null,
      finishedRecording: null,
    });
    mockSelectedTopics.current = new Set(["/topic_a", "/topic_b"]);
    mockGetQueryData.mockReturnValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // --- Initial state ---

  describe("initial state", () => {
    it("has the correct default values", () => {
      const state = useRecordingStore.getState();
      expect(state.delaySec).toBe(0);
      expect(state.stopLiveMonitorDuringRecording).toBe(false);
      expect(state.countdownSec).toBeNull();
      expect(state.isStarting).toBe(false);
      expect(state.isStopping).toBe(false);
      expect(state.message).toBeNull();
      expect(state.finishedRecording).toBeNull();
    });
  });

  // --- setDelay ---

  describe("setDelay", () => {
    it("sets the delay in seconds", () => {
      useRecordingStore.getState().setDelay(5);
      expect(useRecordingStore.getState().delaySec).toBe(5);
    });

    it("can reset to 0", () => {
      useRecordingStore.getState().setDelay(10);
      useRecordingStore.getState().setDelay(0);
      expect(useRecordingStore.getState().delaySec).toBe(0);
    });
  });

  // --- setStopLiveMonitor ---

  describe("setStopLiveMonitor", () => {
    it("turns stop-while-recording on", () => {
      useRecordingStore.getState().setStopLiveMonitor(true);
      expect(useRecordingStore.getState().stopLiveMonitorDuringRecording).toBe(true);
    });

    it("turns stop-while-recording off", () => {
      useRecordingStore.getState().setStopLiveMonitor(true);
      useRecordingStore.getState().setStopLiveMonitor(false);
      expect(useRecordingStore.getState().stopLiveMonitorDuringRecording).toBe(false);
    });
  });

  // --- startRecording ---

  describe("startRecording", () => {
    it("calls the mutation immediately when delay=0", () => {
      useRecordingStore.getState().setDelay(0);
      useRecordingStore.getState().startRecording();

      expect(mockMutateStart).toHaveBeenCalledWith(["/topic_a", "/topic_b"]);
      expect(useRecordingStore.getState().countdownSec).toBeNull();
    });

    it("starts a countdown when delay>0", () => {
      useRecordingStore.getState().setDelay(3);
      useRecordingStore.getState().startRecording();

      expect(useRecordingStore.getState().countdownSec).toBe(3);
      expect(mockMutateStart).not.toHaveBeenCalled();
    });

    it("decrements the countdown by one second", () => {
      useRecordingStore.getState().setDelay(3);
      useRecordingStore.getState().startRecording();

      vi.advanceTimersByTime(1000);
      expect(useRecordingStore.getState().countdownSec).toBe(2);

      vi.advanceTimersByTime(1000);
      expect(useRecordingStore.getState().countdownSec).toBe(1);
    });

    it("calls the mutation after the countdown completes", () => {
      useRecordingStore.getState().setDelay(3);
      useRecordingStore.getState().startRecording();

      vi.advanceTimersByTime(3000);

      expect(useRecordingStore.getState().countdownSec).toBeNull();
      expect(mockMutateStart).toHaveBeenCalledWith(["/topic_a", "/topic_b"]);
    });

    it("tick is a no-op when countdownSec becomes null mid-flight (race guard)", () => {
      useRecordingStore.getState().setDelay(3);
      useRecordingStore.getState().startRecording();

      // Externally clear countdownSec (simulating a race with stopRecording, etc.)
      useRecordingStore.setState({ countdownSec: null });
      vi.advanceTimersByTime(1000);

      // tick exits via the guard clause, so countdownSec stays null and the mutation is not called
      expect(useRecordingStore.getState().countdownSec).toBeNull();
      expect(mockMutateStart).not.toHaveBeenCalled();
    });

    it("clears finishedRecording on start", () => {
      useRecordingStore.setState({
        finishedRecording: {
          name: "old",
          path: "/data/old",
          durationSec: 1,
          messageCount: null,
          topicCount: null,
          size: 0,
        },
      });
      useRecordingStore.getState().startRecording();

      expect(useRecordingStore.getState().finishedRecording).toBeNull();
    });
  });

  // --- stopRecording ---

  describe("stopRecording", () => {
    it("cancels during countdown", () => {
      useRecordingStore.getState().setDelay(5);
      useRecordingStore.getState().startRecording();
      expect(useRecordingStore.getState().countdownSec).toBe(5);

      useRecordingStore.getState().stopRecording();

      expect(useRecordingStore.getState().countdownSec).toBeNull();
      expect(mockShowMessage).toHaveBeenCalledWith("Countdown canceled", "error");
      expect(mockMutateStop).not.toHaveBeenCalled();
    });

    it("calls the stop mutation when not in countdown", () => {
      useRecordingStore.getState().stopRecording();

      expect(mockMutateStop).toHaveBeenCalledWith(undefined);
    });
  });

  // --- toggle ---

  describe("toggle", () => {
    it("does nothing while isStarting", () => {
      useRecordingStore.setState({ isStarting: true });
      useRecordingStore.getState().toggle();

      expect(mockMutateStart).not.toHaveBeenCalled();
      expect(mockMutateStop).not.toHaveBeenCalled();
    });

    it("does nothing while isStopping", () => {
      useRecordingStore.setState({ isStopping: true });
      useRecordingStore.getState().toggle();

      expect(mockMutateStart).not.toHaveBeenCalled();
      expect(mockMutateStop).not.toHaveBeenCalled();
    });

    it("calls stopRecording when recording", () => {
      mockGetQueryData.mockReturnValue({
        data: { is_recording: true },
        status: 200,
      });

      useRecordingStore.getState().toggle();

      expect(mockMutateStop).toHaveBeenCalledWith(undefined);
    });

    it("calls stopRecording (cancel) during countdown", () => {
      useRecordingStore.setState({ countdownSec: 3 });
      useRecordingStore.getState().toggle();

      expect(useRecordingStore.getState().countdownSec).toBeNull();
      expect(mockShowMessage).toHaveBeenCalledWith("Countdown canceled", "error");
    });

    it("starts recording when idle, connected, and a topic is selected", () => {
      // getIsRecording reads the recording-status key; getConnectionStatus reads the SSE key.
      mockGetQueryData.mockImplementation((key?: unknown) =>
        Array.isArray(key) && key[0] === "recording-status"
          ? { data: { is_recording: false }, status: 200 }
          : "connected",
      );

      useRecordingStore.getState().toggle();

      expect(mockMutateStart).toHaveBeenCalled();
    });

    it("does not start when disconnected, and shows a message", () => {
      // recording-status undefined -> not recording; connection status -> disconnected.
      mockGetQueryData.mockImplementation((key?: unknown) =>
        Array.isArray(key) && key[0] === "recording-status" ? undefined : "disconnected",
      );

      useRecordingStore.getState().toggle();

      expect(mockMutateStart).not.toHaveBeenCalled();
      expect(mockShowMessage).toHaveBeenCalledWith("Cannot start recording while disconnected", "error");
    });

    it("does not start when no topic is selected, and shows a message", () => {
      mockSelectedTopics.current = new Set();
      mockGetQueryData.mockImplementation((key?: unknown) =>
        Array.isArray(key) && key[0] === "recording-status"
          ? { data: { is_recording: false }, status: 200 }
          : "connected",
      );

      useRecordingStore.getState().toggle();

      expect(mockMutateStart).not.toHaveBeenCalled();
      expect(mockShowMessage).toHaveBeenCalledWith("Select at least one topic to record", "error");
    });
  });

  // --- clearMessage ---

  describe("clearMessage", () => {
    it("sets the message to null", () => {
      useRecordingStore.setState({ message: { text: "Test", type: "success" } });
      useRecordingStore.getState().clearMessage();

      expect(useRecordingStore.getState().message).toBeNull();
    });

    it("calls clearMessageTimer", () => {
      useRecordingStore.getState().clearMessage();

      expect(mockClearMessageTimer).toHaveBeenCalled();
    });
  });

  // --- dismissFinishedRecording ---

  describe("dismissFinishedRecording", () => {
    it("resets finishedRecording to null", () => {
      useRecordingStore.setState({
        finishedRecording: {
          name: "rec_001",
          path: "/data/rec_001",
          durationSec: 5,
          messageCount: 100,
          topicCount: 2,
          size: 1024,
        },
      });
      useRecordingStore.getState().dismissFinishedRecording();

      expect(useRecordingStore.getState().finishedRecording).toBeNull();
    });
  });
});
