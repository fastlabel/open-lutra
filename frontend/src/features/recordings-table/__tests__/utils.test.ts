import { describe, expect, it } from "vitest";
import type { FileEntry } from "@/api/generated/schemas";
import { applySearchAndFilter, formatRecordingDate, formatSize } from "../utils";

// --- formatSize ---

describe("formatSize", () => {
  it("returns bytes", () => {
    expect(formatSize(500)).toBe("500B");
  });

  it("returns KB", () => {
    expect(formatSize(1536)).toBe("1.5KB");
  });

  it("returns MB", () => {
    expect(formatSize(2.5 * 1024 * 1024)).toBe("2.5MB");
  });

  it("returns GB", () => {
    expect(formatSize(1.2 * 1024 * 1024 * 1024)).toBe("1.2GB");
  });

  it("handles 0 bytes", () => {
    expect(formatSize(0)).toBe("0B");
  });

  it("switches to KB at exactly 1024", () => {
    expect(formatSize(1024)).toBe("1.0KB");
  });
});

// --- applySearchAndFilter ---

describe("applySearchAndFilter", () => {
  const baseEntry = (overrides: Partial<FileEntry>): FileEntry => ({
    name: "rec",
    path: "rec",
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

  const entries: FileEntry[] = [
    baseEntry({ name: "task_001" }),
    baseEntry({ name: "task_002" }),
    baseEntry({ name: "demo_003" }),
    baseEntry({ name: "demo_004" }),
  ];

  it("returns all entries when no filters are applied", () => {
    expect(applySearchAndFilter(entries, "")).toHaveLength(4);
  });

  it("narrows folders by search text", () => {
    const result = applySearchAndFilter(entries, "task");
    expect(result.map((e) => e.name)).toEqual(["task_001", "task_002"]);
  });

  it("search text is case-insensitive", () => {
    const result = applySearchAndFilter(entries, "TASK");
    expect(result).toHaveLength(2);
  });

  // --- taskFilter ---

  const taskEntries: FileEntry[] = [
    baseEntry({ name: "a", task_name: "pick" }),
    baseEntry({ name: "b", task_name: "pick" }),
    baseEntry({ name: "c", task_name: "place" }),
    baseEntry({ name: "d", task_name: null }),
  ];

  it("taskFilter=null does not filter by task", () => {
    expect(applySearchAndFilter(taskEntries, "", null)).toHaveLength(4);
  });

  it("filters by exact match when taskFilter is set to a task_name", () => {
    const result = applySearchAndFilter(taskEntries, "", "pick");
    expect(result.map((e) => e.name)).toEqual(["a", "b"]);
  });

  it('taskFilter="" returns only recordings without a task_name', () => {
    const result = applySearchAndFilter(taskEntries, "", "");
    expect(result.map((e) => e.name)).toEqual(["d"]);
  });

  it("AND-combines taskFilter with search text", () => {
    const result = applySearchAndFilter(taskEntries, "a", "pick");
    expect(result.map((e) => e.name)).toEqual(["a"]);
  });
});

// --- formatRecordingDate ---

describe("formatRecordingDate", () => {
  it("returns '---' for null", () => {
    expect(formatRecordingDate(null)).toBe("---");
  });

  it("formats a nanosecond timestamp as 'MM/DD HH:mm'", () => {
    // 2024-01-15 09:30:00 UTC
    const ns = new Date("2024-01-15T09:30:00Z").getTime() * 1_000_000;
    const result = formatRecordingDate(ns);
    // Depends on the local timezone, so only check the format
    expect(result).toMatch(/^\d{2}\/\d{2} \d{2}:\d{2}$/);
  });
});
