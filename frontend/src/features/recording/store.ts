/** State store for recording operations.
 *
 * Centralizes countdown, delay configuration, and start/stop logic.
 * CenterPanel handles display only; actions can also be invoked directly from keyboard shortcuts.
 */
import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";
import { getGetRecordingStatusQueryKey } from "@/api/generated/recording/recording";
import type { RecordingStatus } from "@/api/generated/schemas";
import { useLiveTopicsStore } from "@/features/live-topics";
import type { SseConnectionStatus } from "@/hooks/use-topics-stream";
import { queryClient } from "@/lib/query-client";
import { sseKeys } from "@/lib/query-keys";
import { toast } from "@/stores/toast-store";
import { createTimer } from "./create-timer";
import { startRecordingMutation, stopRecordingMutation } from "./mutations";
import * as sounds from "./sounds";

/** Available delay options. */
export const DELAY_OPTIONS = [0, 3, 5, 10] as const;

/** Info about the just-finished recording (used to render the completion banner). */
export interface FinishedRecording {
  /** Folder name. */
  name: string;
  /** Path relative to output_dir. */
  path: string;
  /** Recording duration in seconds. */
  durationSec: number;
  /** Total message count (null when unavailable). */
  messageCount: number | null;
  /** Topic count (null when unavailable). */
  topicCount: number | null;
  /** Total file size in bytes. */
  size: number;
}

interface RecordingStore {
  /** Delay in seconds. */
  delaySec: number;
  /** Whether to stop live monitoring while recording is in progress. */
  stopLiveMonitorDuringRecording: boolean;
  /** Whether to play notification tones on countdown / start / stop. */
  soundEnabled: boolean;
  /** Seconds remaining in countdown (null = not counting down). */
  countdownSec: number | null;
  /** A start request is in flight. */
  isStarting: boolean;
  /** A stop request is in flight. */
  isStopping: boolean;
  /** Info about the most recently finished recording (rendered as a banner; dismissed with × or cleared when a new recording starts). */
  finishedRecording: FinishedRecording | null;

  /** Update the delay setting (auto-persisted via persist middleware). */
  setDelay: (sec: number) => void;
  /** Toggle "stop live monitoring while recording" on/off. */
  setStopLiveMonitor: (enabled: boolean) => void;
  /** Toggle recording notification tones on/off. */
  setSoundEnabled: (enabled: boolean) => void;
  /** Start recording (honors the delay). */
  startRecording: () => void;
  /** Stop recording (cancels the countdown if one is active). */
  stopRecording: () => void;
  /** Dispatch start/stop based on loading/isRecording/isCountingDown. */
  toggle: () => void;
  /** Close the completion banner. */
  dismissFinishedRecording: () => void;
}

// --- Timer ---
const countdownTimer = createTimer();

/** Read isRecording synchronously from the TanStack Query cache. */
function getIsRecording(): boolean {
  const resp = queryClient.getQueryData<{ data: RecordingStatus; status: number }>(getGetRecordingStatusQueryKey());
  return resp?.status === 200 ? resp.data.is_recording : false;
}

/** Read the SSE connection status synchronously from the TanStack Query cache. */
function getConnectionStatus(): SseConnectionStatus | undefined {
  return queryClient.getQueryData<SseConnectionStatus>(sseKeys.connectionStatus());
}

/** Countdown one-second tick (recursive setTimeout). */
function tick() {
  const { countdownSec, soundEnabled } = useRecordingStore.getState();
  if (countdownSec === null) return;
  if (countdownSec <= 1) {
    // Final handoff: the start chime (mutations.onSuccess) stands in for a tick here.
    useRecordingStore.setState({ countdownSec: null }, false, "tickComplete");
    startRecordingMutation.mutate([...useLiveTopicsStore.getState().selectedTopics]);
    return;
  }
  if (soundEnabled) sounds.playTick();
  useRecordingStore.setState({ countdownSec: countdownSec - 1 }, false, "tick");
  countdownTimer.set(tick, 1000);
}

export const useRecordingStore = create<RecordingStore>()(
  devtools(
    persist(
      (set, get) => ({
        delaySec: 0,
        stopLiveMonitorDuringRecording: false,
        soundEnabled: true,
        countdownSec: null,
        isStarting: false,
        isStopping: false,
        finishedRecording: null,

        setDelay: (sec) => set({ delaySec: sec }, false, "setDelay"),
        setStopLiveMonitor: (enabled) => set({ stopLiveMonitorDuringRecording: enabled }, false, "setStopLiveMonitor"),
        setSoundEnabled: (enabled) => set({ soundEnabled: enabled }, false, "setSoundEnabled"),

        startRecording: () => {
          // Auto-close any lingering banner from the previous recording.
          set({ finishedRecording: null }, false, "clearFinishedOnStart");
          const { delaySec, soundEnabled } = get();
          // Resume the audio context from within this gesture so the async start chime can play.
          if (soundEnabled) sounds.unlock();
          if (delaySec <= 0) {
            startRecordingMutation.mutate([...useLiveTopicsStore.getState().selectedTopics]);
            return;
          }
          if (soundEnabled) sounds.playTick();
          set({ countdownSec: delaySec }, false, "startCountdown");
          countdownTimer.set(tick, 1000);
        },

        stopRecording: () => {
          const { countdownSec, soundEnabled } = get();
          // Resume the audio context from within this gesture so the async stop chime can play.
          if (soundEnabled) sounds.unlock();
          if (countdownSec !== null) {
            countdownTimer.clear();
            set({ countdownSec: null }, false, "cancelCountdown");
            toast.error("Countdown canceled");
            return;
          }
          stopRecordingMutation.mutate(undefined);
        },

        toggle: () => {
          const { isStarting, isStopping, countdownSec, stopRecording, startRecording } = get();
          if (isStarting || isStopping) return;
          if (getIsRecording() || countdownSec !== null) {
            stopRecording();
            return;
          }
          // Mirror the record button's start preconditions (record-button.tsx): require a live
          // connection and at least one selected topic, with feedback when a start is refused.
          if (getConnectionStatus() !== "connected") {
            toast.error("Cannot start recording while disconnected");
            return;
          }
          if (useLiveTopicsStore.getState().selectedTopics.size === 0) {
            toast.error("Select at least one topic to record");
            return;
          }
          startRecording();
        },

        dismissFinishedRecording: () => set({ finishedRecording: null }, false, "dismissFinishedRecording"),
      }),
      {
        name: "recording-settings",
        // zustand persist configuration. Persist only delaySec and stopLiveMonitorDuringRecording to localStorage.
        // This is a trivial field-pick, so exclude it from coverage.
        /* v8 ignore start */
        partialize: (state) => ({
          delaySec: state.delaySec,
          stopLiveMonitorDuringRecording: state.stopLiveMonitorDuringRecording,
          soundEnabled: state.soundEnabled,
        }),
        /* v8 ignore stop */
      },
    ),
    { name: "RecordingStore" },
  ),
);
