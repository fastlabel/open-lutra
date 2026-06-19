/** Record button: white-bordered button (red when idle, dark when recording). An outer gray border pulses while recording. */

import { useLiveTopicsStore } from "@/features/live-topics";
import { useIsRecording } from "@/hooks/use-api";
import { useConnectionStatus } from "@/hooks/use-topics-stream";
import { useRecordingStore } from "./store";
import { useRecordShortcut } from "./use-record-shortcut";

export function RecordButton() {
  const isRecording = useIsRecording();
  const isCountingDown = useRecordingStore((s) => s.countdownSec !== null);
  const loading = useRecordingStore((s) => s.isStarting || s.isStopping);
  const startRecording = useRecordingStore((s) => s.startRecording);
  const stopRecording = useRecordingStore((s) => s.stopRecording);
  const connectionStatus = useConnectionStatus();
  const hasSelectedTopics = useLiveTopicsStore((s) => s.selectedTopics.size > 0);

  const active = isRecording || isCountingDown;
  const label = active ? "STOP" : "START REC";
  // Only when not recording do we require "connected" and "at least one topic selected". During recording/countdown we allow the press so the user can stop.
  const cannotStart = !active && (connectionStatus !== "connected" || !hasSelectedTopics);
  const disabled = loading || cannotStart;

  // --- Side effects ---
  // Space toggles recording (keyboard / foot-pedal), mirroring this button. See use-record-shortcut.
  useRecordShortcut();

  return (
    // Show and pulse the outer gray border only while recording. pulse-border animates border-color only,
    // not the children's opacity (so the inner STOP icon and text do not pulse).
    <div
      className={`rounded-xl p-[3px] border-2 ${
        active ? "animate-[pulse-border_1.4s_ease-in-out_infinite]" : "border-transparent"
      }`}
    >
      <button
        type="button"
        disabled={disabled}
        onClick={active ? stopRecording : startRecording}
        title={active ? "Stop recording (Space)" : "Start recording (Space)"}
        aria-label={label}
        aria-pressed={active}
        className={`flex h-20 w-[200px] cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-white text-[14px] font-bold tracking-wider text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          active ? "bg-card hover:bg-card/80" : "bg-red-500 hover:bg-red-500/90"
        }`}
      >
        {/* Icon: morph between a circle (start) and a rounded square (stop) via border-radius */}
        <span className="flex h-7 w-7 items-center justify-center">
          <span
            className={`block bg-white transition-[border-radius,transform] duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
              active ? "h-6 w-6 rounded-[3px]" : "h-7 w-7 rounded-full"
            }`}
          />
        </span>
        <span key={label} className="animate-[fade-in_200ms_ease-out]">
          {label}
        </span>
      </button>
    </div>
  );
}
