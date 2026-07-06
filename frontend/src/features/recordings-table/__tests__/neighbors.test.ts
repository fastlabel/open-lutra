import { describe, expect, it } from "vitest";
import type { FileEntry } from "@/api/generated/schemas";
import { computeNeighbors } from "../neighbors";

const entry = (name: string, overrides: Partial<FileEntry> = {}): FileEntry => ({
  name,
  path: name,
  size: 0,
  modified_at: 0,
  topic_count: null,
  recording_start_ns: null,
  duration_ns: null,
  message_count: null,
  has_quality_report: false,
  validation_overall_status: null,
  upload_status: null,
  task_name: null,
  recording_config_name: null,
  tags: [],
  ...overrides,
});

describe("computeNeighbors", () => {
  const list = [entry("a"), entry("b"), entry("c")];

  it("returns the surrounding entries for a middle item", () => {
    const n = computeNeighbors(list, list, "b");
    expect(n.prev?.path).toBe("a");
    expect(n.next?.path).toBe("c");
    expect(n).toMatchObject({ index: 1, total: 3, currentExists: true });
  });

  it("has no prev at the head and no next at the tail (no wrap-around)", () => {
    const head = computeNeighbors(list, list, "a");
    expect(head.prev).toBeNull();
    expect(head.next?.path).toBe("b");

    const tail = computeNeighbors(list, list, "c");
    expect(tail.prev?.path).toBe("b");
    expect(tail.next).toBeNull();
  });

  it("walks the filtered list when the current recording is part of it", () => {
    const filtered = [entry("a"), entry("c")];
    const n = computeNeighbors(list, filtered, "a");
    expect(n.prev).toBeNull();
    expect(n.next?.path).toBe("c");
    expect(n.total).toBe(2);
  });

  it("falls back to the full list when the current recording is excluded by the filter", () => {
    const filtered = [entry("a"), entry("c")];
    const n = computeNeighbors(list, filtered, "b");
    expect(n.prev?.path).toBe("a");
    expect(n.next?.path).toBe("c");
    expect(n).toMatchObject({ index: 1, total: 3, currentExists: true });
  });

  it("reports currentExists=false with no neighbors when the recording is absent from the full list", () => {
    const n = computeNeighbors(list, [], "missing");
    expect(n).toMatchObject({ prev: null, next: null, index: -1, total: 3, currentExists: false });
  });

  it("handles an empty list", () => {
    const n = computeNeighbors([], [], "a");
    expect(n).toMatchObject({ prev: null, next: null, index: -1, total: 0, currentExists: false });
  });
});
