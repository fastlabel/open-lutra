/** Soft green glow around the viewport edge while a recording is in progress, so the operator can
 * tell at a glance (or in peripheral vision) that recording is running. Clicks pass through. */
import { useIsRecording } from "@/hooks/use-api";

export function RecordingGlow() {
  // --- Server state ---
  const isRecording = useIsRecording();

  if (!isRecording) return null;

  return (
    <div
      aria-hidden
      data-testid="recording-glow"
      // z-40 keeps it under dialogs and popovers (z-50) and toasts (z-[100]).
      className="pointer-events-none fixed inset-0 z-40 animate-[recording-glow_2.4s_ease-in-out_infinite] shadow-[inset_0_0_0_6px_rgba(34,197,94,0.85),inset_0_0_40px_8px_rgba(34,197,94,0.4)] motion-reduce:animate-none"
    />
  );
}
