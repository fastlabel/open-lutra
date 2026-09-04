import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TopicInfo } from "@/api/generated/schemas";
import { sseKeys } from "@/lib/query-keys";
import { useTopicsStream } from "../use-topics-stream";

// A minimal EventSource stand-in: capture listeners and let tests drive the
// connection lifecycle (open / events / reconnect) synchronously.
class FakeEventSource {
  constructor(public readonly url: string) {}
  private readonly listeners: Record<string, (e: MessageEvent) => void> = {};
  public onopen: ((this: EventSource, ev: Event) => unknown) | null = null;
  public onerror: ((this: EventSource, ev: Event) => unknown) | null = null;
  public closed = false;

  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    this.listeners[type] = fn;
  }
  open() {
    this.onopen?.call(this as unknown as EventSource, new Event("open"));
  }
  emit(type: string, data: unknown) {
    this.listeners[type]?.(new MessageEvent(type, { data: JSON.stringify(data) }));
  }
  close() {
    this.closed = true;
  }
}

let lastSource: FakeEventSource | undefined;

beforeEach(() => {
  lastSource = undefined;
  class CapturingEventSource extends FakeEventSource {
    constructor(url: string) {
      super(url);
      lastSource = this;
    }
  }
  vi.stubGlobal("EventSource", CapturingEventSource);
  // The hook pauses/resumes backend monitoring via fetch on mount/unmount.
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response()));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function makeTopic(name: string, overrides: Partial<TopicInfo> = {}): TopicInfo {
  return {
    name,
    msg_type: "std_msgs/msg/String",
    actual_hz: 0,
    status: "inactive",
    message_count: 0,
    is_subscribed: false,
    baseline_hz: null,
    baseline_fixed: false,
    loss_rate: 0,
    drop_count: 0,
    continuity_score: 1,
    qos_reliability: "",
    ...overrides,
  };
}

function renderWithClient<T>(callback: () => T) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { ...renderHook(callback, { wrapper }), client };
}

describe("useTopicsStream (topic_stats replace/merge lifecycle)", () => {
  it("replaces the cached list on the first event after connect", () => {
    const { client } = renderWithClient(() => {
      useTopicsStream();
    });

    // Stale rows from a previous connection must not survive the first event.
    client.setQueryData(sseKeys.topicStats(), [makeTopic("/stale")]);

    const a = makeTopic("/a");
    act(() => {
      lastSource?.open();
      lastSource?.emit("topic_stats", [a]);
    });

    expect(client.getQueryData<TopicInfo[]>(sseKeys.topicStats())).toEqual([a]);
  });

  it("merges later events into the cached list", () => {
    const { client } = renderWithClient(() => {
      useTopicsStream();
    });

    const a = makeTopic("/a");
    const b = makeTopic("/b");
    const changedA = makeTopic("/a", { actual_hz: 10, status: "ok" });
    act(() => {
      lastSource?.open();
      lastSource?.emit("topic_stats", [a, b]);
      lastSource?.emit("topic_stats", [changedA]);
    });

    // /b survives the second event: it is a merge, not a replace.
    expect(client.getQueryData<TopicInfo[]>(sseKeys.topicStats())).toEqual([changedA, b]);
  });

  it("keeps the cached list for an empty tick (keep-alive)", () => {
    const { client } = renderWithClient(() => {
      useTopicsStream();
    });

    const a = makeTopic("/a");
    act(() => {
      lastSource?.open();
      lastSource?.emit("topic_stats", [a]);
      lastSource?.emit("topic_stats", []);
    });

    expect(client.getQueryData<TopicInfo[]>(sseKeys.topicStats())).toEqual([a]);
  });

  it("re-arms the replace when onopen fires again after a reconnect", () => {
    const { client } = renderWithClient(() => {
      useTopicsStream();
    });

    const a = makeTopic("/a");
    const b = makeTopic("/b");
    act(() => {
      lastSource?.open();
      lastSource?.emit("topic_stats", [a, b]);
    });

    // Backend restarted: EventSource reconnects (onopen fires on the same
    // instance) and the first event of the new connection carries only the
    // rows the new backend knows — /a must not stay frozen in the cache.
    act(() => {
      lastSource?.open();
      lastSource?.emit("topic_stats", [b]);
    });

    expect(client.getQueryData<TopicInfo[]>(sseKeys.topicStats())).toEqual([b]);
  });
});
