import { describe, expect, it } from "vitest";
import type { FileEntry } from "@/api/generated/schemas";
import {
  buildTagRows,
  cycleTagCheck,
  newTagRow,
  type TagRow,
  tagDelta,
  tagRequest,
  withTagChecked,
} from "../bulk-tags";

function makeEntry(name: string, tags: string[]): FileEntry {
  return {
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
    tags,
    metadata: {},
  };
}

const row = (overrides: Partial<TagRow>): TagRow => ({
  tag: "t",
  count: 1,
  presence: "some",
  check: "mixed",
  ...overrides,
});

describe("buildTagRows", () => {
  it("counts each tag once per entry, orders by count then name, and checks only tags on every entry", () => {
    const rows = buildTagRows(
      [
        makeEntry("a", ["good", "retry", "retry"]),
        makeEntry("b", ["good", "blurry"]),
        makeEntry("c", ["good", "blurry"]),
      ],
      3,
    );

    expect(rows).toEqual([
      { tag: "good", count: 3, presence: "all", check: "checked" },
      { tag: "blurry", count: 2, presence: "some", check: "mixed" },
      { tag: "retry", count: 1, presence: "some", check: "mixed" },
    ]);
  });

  it("returns no rows when the entries carry no tags", () => {
    expect(buildTagRows([makeEntry("a", []), makeEntry("b", [])], 2)).toEqual([]);
    expect(buildTagRows([], 0)).toEqual([]);
  });

  it("judges presence by the selection size, so a selected recording missing from the entries keeps tags mixed", () => {
    expect(buildTagRows([makeEntry("a", ["good"])], 2)).toEqual([
      { tag: "good", count: 1, presence: "some", check: "mixed" },
    ]);
  });
});

describe("newTagRow", () => {
  it("starts checked so that saving adds the tag", () => {
    expect(newTagRow("reviewed")).toEqual({
      tag: "reviewed",
      count: 0,
      presence: "none",
      check: "checked",
    });
  });
});

describe("withTagChecked", () => {
  it("checks an existing row in place without touching the others", () => {
    const rows = [row({ tag: "retry", check: "mixed" }), row({ tag: "good", presence: "all", check: "unchecked" })];

    expect(withTagChecked(rows, "good")).toEqual([rows[0], { ...rows[1], check: "checked" }]);
  });

  it("appends any other tag as a new checked row", () => {
    const rows = [row({ tag: "retry" })];

    expect(withTagChecked(rows, "reviewed")).toEqual([...rows, newTagRow("reviewed")]);
  });
});

describe("cycleTagCheck", () => {
  it("toggles a tag that is on every recording", () => {
    const all = row({ presence: "all", check: "checked" });
    expect(cycleTagCheck(all)).toBe("unchecked");
    expect(cycleTagCheck({ ...all, check: "unchecked" })).toBe("checked");
  });

  it("cycles a tag that is on some recordings through mixed, checked, unchecked", () => {
    const some = row({ presence: "some", check: "mixed" });
    expect(cycleTagCheck(some)).toBe("checked");
    expect(cycleTagCheck({ ...some, check: "checked" })).toBe("unchecked");
    expect(cycleTagCheck({ ...some, check: "unchecked" })).toBe("mixed");
  });

  it("toggles a new tag", () => {
    const none = newTagRow("reviewed");
    expect(cycleTagCheck(none)).toBe("unchecked");
    expect(cycleTagCheck({ ...none, check: "unchecked" })).toBe("checked");
  });
});

describe("tagDelta", () => {
  it("adds when checked unless already on every recording", () => {
    expect(tagDelta(row({ presence: "some", check: "checked" }))).toBe("add");
    expect(tagDelta(row({ presence: "none", check: "checked" }))).toBe("add");
    expect(tagDelta(row({ presence: "all", check: "checked" }))).toBeNull();
  });

  it("removes when unchecked unless on no recording", () => {
    expect(tagDelta(row({ presence: "all", check: "unchecked" }))).toBe("remove");
    expect(tagDelta(row({ presence: "some", check: "unchecked" }))).toBe("remove");
    expect(tagDelta(row({ presence: "none", check: "unchecked" }))).toBeNull();
  });

  it("does nothing while a tag on some recordings stays mixed", () => {
    expect(tagDelta(row({ presence: "some", check: "mixed" }))).toBeNull();
  });
});

describe("tagRequest", () => {
  it("splits the rows into add_tags and remove_tags in row order", () => {
    expect(
      tagRequest([
        row({ tag: "good", presence: "all", check: "unchecked" }),
        row({ tag: "retry", presence: "some", check: "checked" }),
        row({ tag: "blurry", presence: "some", check: "mixed" }),
        row({ tag: "night", presence: "some", check: "unchecked" }),
        newTagRow("reviewed"),
      ]),
    ).toEqual({
      add_tags: ["retry", "reviewed"],
      remove_tags: ["good", "night"],
    });
  });
});
