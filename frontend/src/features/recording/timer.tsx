/** Recording timer display. Computes the value and style based on current state. */
import { memo } from "react";
import { useIsRecording, useRecordingStatus } from "@/hooks/use-api";
import { useRecordingStore } from "./store";

/** Format seconds as MM:SS (supports negative values). */
function formatTime(seconds: number): string {
  const abs = Math.abs(seconds);
  const mins = Math.floor(abs / 60);
  const secs = Math.floor(abs % 60);
  const formatted = `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  return seconds < 0 ? `-${formatted}` : formatted;
}

export const Timer = memo(function Timer({ className: override }: { className?: string } = {}) {
  const { data: status } = useRecordingStatus();
  const isRecording = useIsRecording();
  const countdownSec = useRecordingStore((state) => state.countdownSec);
  const delaySec = useRecordingStore((state) => state.delaySec);
  const isCountingDown = countdownSec !== null;

  // Fallback (font size + color) used when the caller does not override className.
  let value: string;
  let fallback: string;
  if (isCountingDown) {
    value = formatTime(-countdownSec);
    fallback = "text-[13px] text-amber-600 dark:text-amber-400";
  } else if (isRecording) {
    value = formatTime(status?.elapsed_sec ?? 0);
    fallback = "text-[13px] text-red-600 dark:text-red-400";
  } else if (delaySec > 0) {
    value = formatTime(-delaySec);
    fallback = "text-[13px] text-muted-foreground";
  } else {
    value = "00:00";
    fallback = "text-[13px] text-muted-foreground";
  }

  return <span className={`font-mono tabular-nums ${override ?? fallback}`}>{value}</span>;
});
