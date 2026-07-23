/** Notification tones for recording state changes (Web Audio, no asset files).
 *
 * A single AudioContext is created lazily and shared across tones. Browsers keep
 * it suspended until a user gesture resumes it, so unlock() must run from a gesture
 * handler (the start/stop press) before the async start/stop chimes can fire.
 */

/** A single tone in a sequence: a sine wave at `freq` Hz lasting `durationMs`. */
interface ToneStep {
  freq: number;
  durationMs: number;
}

/** Peak gain of each tone, kept low so the beeps stay unobtrusive. */
const PEAK_GAIN = 0.15;

let ctx: AudioContext | null = null;

/** Lazily create the shared AudioContext; null when Web Audio is unavailable (SSR / jsdom). */
function getContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Ctor =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  ctx ??= new Ctor();
  return ctx;
}

/** Resume the audio context from within a user gesture so the later async chimes can play. */
export function unlock(): void {
  const c = getContext();
  if (c?.state === "suspended") void c.resume();
}

/** Play a sequence of tones back-to-back with a short click-free envelope. */
function playSequence(steps: ToneStep[]): void {
  const c = getContext();
  if (!c) return;
  let t = c.currentTime;
  for (const { freq, durationMs } of steps) {
    const dur = durationMs / 1000;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq, t);
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(PEAK_GAIN, t + 0.01);
    gain.gain.linearRampToValueAtTime(0, t + dur);
    osc.connect(gain).connect(c.destination);
    osc.start(t);
    osc.stop(t + dur);
    t += dur;
  }
}

/** Countdown tick: a single short blip. */
export function playTick(): void {
  playSequence([{ freq: 880, durationMs: 70 }]);
}

/** Recording started: a rising two-tone chime. */
export function playStart(): void {
  playSequence([
    { freq: 660, durationMs: 90 },
    { freq: 990, durationMs: 120 },
  ]);
}

/** Recording stopped: a falling two-tone chime. */
export function playStop(): void {
  playSequence([
    { freq: 660, durationMs: 90 },
    { freq: 440, durationMs: 140 },
  ]);
}
