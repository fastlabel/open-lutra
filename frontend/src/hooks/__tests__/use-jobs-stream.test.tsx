import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getGetRecordingsQueryKey } from "@/api/generated/recordings/recordings";
import type { JobSchema } from "@/api/generated/schemas";
import { getGetValidationQueryKey } from "@/api/generated/validation/validation";
import { useJobsStream, useUploadJob } from "../use-jobs-stream";

// A minimal EventSource stand-in: capture listeners and let tests dispatch
// fake job events synchronously.
class FakeEventSource {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- mirrors the EventSource constructor signature
  constructor(public readonly url: string) {}
  private readonly listeners: Record<string, (e: MessageEvent) => void> = {};
  public onerror: ((this: EventSource, ev: Event) => unknown) | null = null;
  public closed = false;

  addEventListener(type: string, fn: (e: MessageEvent) => void) {
    this.listeners[type] = fn;
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
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function makeJob(overrides: Partial<JobSchema>): JobSchema {
  return {
    job_id: "j-validation-1",
    type: "validation",
    folder: "rec_001",
    status: "completed",
    progress: { step: "", step_label: "", current: 0, total: 1 },
    error: null,
    created_at: "2026-05-25T00:00:00",
    started_at: null,
    finished_at: null,
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

describe("useJobsStream", () => {
  it("upserts the running validation job into the jobs cache", () => {
    const { client } = renderWithClient(() => {
      useJobsStream();
    });

    expect(lastSource).toBeDefined();
    act(() => {
      lastSource?.emit("job_started", makeJob({ job_id: "j-validation-1", type: "validation", status: "running" }));
    });

    // Read the cache directly: useQuery's hook subscription does not always
    // re-render synchronously inside renderHook even when wrapped in act().
    const cached = client.getQueryData<JobSchema[]>(["sse", "jobs"]);
    expect(cached).toHaveLength(1);
    expect(cached?.[0]?.type).toBe("validation");
    expect(cached?.[0]?.status).toBe("running");
  });

  it("invalidates /api/validation and /api/recordings when a validation job completes", () => {
    const { client } = renderWithClient(() => {
      useJobsStream();
    });

    // Seed caches so we can observe their dataUpdatedAt change after invalidation.
    client.setQueryData(getGetValidationQueryKey({ path: "rec_001" }), { stub: true });
    client.setQueryData(getGetRecordingsQueryKey(), { stub: true });
    const invalidate = vi.spyOn(client, "invalidateQueries");

    act(() => {
      lastSource?.emit("job_completed", makeJob({ job_id: "j-validation-1", type: "validation", status: "completed" }));
    });

    // Both keys are invalidated (one call per key).
    const calls = invalidate.mock.calls.map((c) => c[0]?.queryKey);
    expect(calls).toContainEqual(getGetValidationQueryKey());
    expect(calls).toContainEqual(getGetRecordingsQueryKey());
    const cached = client.getQueryData<JobSchema[]>(["sse", "jobs"]);
    expect(cached?.[0]?.status).toBe("completed");
  });
});

function renderUploadJob(folder: string, jobs: JobSchema[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // Seed the cache before rendering so the first render already reflects it.
  client.setQueryData<JobSchema[]>(["sse", "jobs"], jobs);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useUploadJob(folder), { wrapper });
}

describe("useUploadJob", () => {
  it("returns the active upload job scoped to the given folder", () => {
    const { result } = renderUploadJob("rec_001", [
      makeJob({ job_id: "u1", type: "upload", folder: "rec_001", status: "running" }),
      makeJob({ job_id: "u2", type: "upload", folder: "other", status: "running" }),
      makeJob({ job_id: "v1", type: "validation", folder: "rec_001", status: "running" }),
    ]);
    expect(result.current?.job_id).toBe("u1");
  });

  it("returns undefined when the folder has no queued/running upload job", () => {
    const { result } = renderUploadJob("rec_001", [
      makeJob({ job_id: "u1", type: "upload", folder: "rec_001", status: "completed" }),
    ]);
    expect(result.current).toBeUndefined();
  });
});
