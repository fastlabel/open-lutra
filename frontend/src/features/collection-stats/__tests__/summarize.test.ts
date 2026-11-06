import { describe, expect, it } from "vitest";
import type { FileEntry } from "@/api/generated/schemas";
import { summarize } from "../summarize";

const SEC = 1_000_000_000;

function makeEntry(overrides: Partial<FileEntry> = {}): FileEntry {
  return {
    name: "rec",
    path: "rec",
    size: 0,
    modified_at: 0,
    topic_count: null,
    recording_start_ns: 0,
    duration_ns: 10 * SEC,
    message_count: null,
    has_quality_report: false,
    validation_overall_status: "pass",
    upload_status: null,
    task_name: null,
    recording_config_name: null,
    tags: [],
    metadata: {},
    ...overrides,
  };
}

describe("summarize", () => {
  it("returns zeros for a day with no recordings", () => {
    expect(summarize([])).toEqual({ usable: { count: 0, durationNs: 0 }, total: 0, failed: 0, errors: 0, pending: 0 });
  });

  it("counts warn as usable", () => {
    const summary = summarize([makeEntry({ validation_overall_status: "warn", duration_ns: 7 * SEC })]);
    expect(summary.usable).toEqual({ count: 1, durationNs: 7 * SEC });
    expect(summary.pending).toBe(0);
  });

  it("counts a recording without a validation result as pending, not usable", () => {
    const summary = summarize([makeEntry({ validation_overall_status: null })]);
    expect(summary.usable.count).toBe(0);
    expect(summary.pending).toBe(1);
  });

  it("counts an unrecognized status as pending", () => {
    const summary = summarize([makeEntry({ validation_overall_status: "something-new" })]);
    expect(summary.usable.count).toBe(0);
    expect(summary.pending).toBe(1);
  });

  it("counts error separately from fail", () => {
    const summary = summarize([
      makeEntry({ validation_overall_status: "fail" }),
      makeEntry({ validation_overall_status: "error" }),
    ]);
    expect(summary).toMatchObject({ failed: 1, errors: 1, total: 2, usable: { count: 0, durationNs: 0 } });
  });

  it("counts a usable recording without a duration as zero seconds", () => {
    const summary = summarize([makeEntry({ duration_ns: null }), makeEntry({ duration_ns: 5 * SEC })]);
    expect(summary.usable).toEqual({ count: 2, durationNs: 5 * SEC });
  });

  it("makes usable volume the headline and breaks down the rest (spec example)", () => {
    const entries = [
      ...Array.from({ length: 9 }, () => makeEntry({ validation_overall_status: "pass", duration_ns: 10 * SEC })),
      makeEntry({ validation_overall_status: "warn", duration_ns: 20 * SEC }),
      makeEntry({ validation_overall_status: "fail", duration_ns: 30 * SEC }),
      makeEntry({ validation_overall_status: null, duration_ns: 40 * SEC }),
    ];
    expect(summarize(entries)).toEqual({
      usable: { count: 10, durationNs: 110 * SEC },
      total: 12,
      failed: 1,
      errors: 0,
      pending: 1,
    });
  });
});
