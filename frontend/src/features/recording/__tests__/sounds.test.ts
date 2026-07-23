import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// --- Fake Web Audio graph (jsdom has no AudioContext) ---

interface OscStub {
  type: string;
  frequency: { setValueAtTime: (freq: number, when: number) => void };
  connect: (node: unknown) => unknown;
  start: (when: number) => void;
  stop: (when: number) => void;
  freqs: number[];
}

let contexts: FakeAudioContext[] = [];

class FakeAudioContext {
  state: "suspended" | "running" = "suspended";
  currentTime = 0;
  destination = {};
  resume = vi.fn(() => {
    this.state = "running";
    return Promise.resolve();
  });
  oscillators: OscStub[] = [];

  constructor() {
    contexts.push(this);
  }

  createOscillator(): OscStub {
    const osc: OscStub = {
      type: "sine",
      freqs: [],
      frequency: { setValueAtTime: (freq: number) => osc.freqs.push(freq) },
      connect: (node: unknown) => node,
      start: vi.fn(),
      stop: vi.fn(),
    };
    this.oscillators.push(osc);
    return osc;
  }

  createGain() {
    return {
      gain: { setValueAtTime: vi.fn(), linearRampToValueAtTime: vi.fn() },
      connect: (node: unknown) => node,
    };
  }
}

function installAudioContext(Ctor: typeof FakeAudioContext | undefined) {
  window.AudioContext = Ctor as unknown as typeof AudioContext;
}

async function loadSounds() {
  vi.resetModules();
  return import("../sounds");
}

describe("recording sounds", () => {
  beforeEach(() => {
    contexts = [];
    installAudioContext(FakeAudioContext);
  });

  afterEach(() => {
    installAudioContext(undefined);
  });

  it("unlock resumes a suspended context", async () => {
    const sounds = await loadSounds();
    sounds.unlock();

    expect(contexts).toHaveLength(1);
    expect(contexts[0].resume).toHaveBeenCalledTimes(1);
    expect(contexts[0].state).toBe("running");
  });

  it("unlock does not resume an already-running context", async () => {
    const sounds = await loadSounds();
    sounds.unlock(); // creates + resumes
    sounds.unlock(); // already running

    expect(contexts).toHaveLength(1);
    expect(contexts[0].resume).toHaveBeenCalledTimes(1);
  });

  it("reuses a single shared context across tones", async () => {
    const sounds = await loadSounds();
    sounds.playTick();
    sounds.playStart();

    expect(contexts).toHaveLength(1);
  });

  it("playTick emits one blip", async () => {
    const sounds = await loadSounds();
    sounds.playTick();

    expect(contexts[0].oscillators.map((o) => o.freqs[0])).toEqual([880]);
  });

  it("playStart is a rising two-tone chime", async () => {
    const sounds = await loadSounds();
    sounds.playStart();

    expect(contexts[0].oscillators.map((o) => o.freqs[0])).toEqual([660, 990]);
  });

  it("playStop is a falling two-tone chime", async () => {
    const sounds = await loadSounds();
    sounds.playStop();

    expect(contexts[0].oscillators.map((o) => o.freqs[0])).toEqual([660, 440]);
  });

  it("is a no-op when Web Audio is unavailable", async () => {
    installAudioContext(undefined);
    const sounds = await loadSounds();

    expect(() => {
      sounds.unlock();
      sounds.playStart();
      sounds.playStop();
      sounds.playTick();
    }).not.toThrow();
    expect(contexts).toHaveLength(0);
  });
});
