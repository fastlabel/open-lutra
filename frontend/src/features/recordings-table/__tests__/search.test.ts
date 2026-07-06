import { describe, expect, it } from "vitest";
import { validateRecordingsSearch } from "../search";

describe("validateRecordingsSearch", () => {
  it("returns an empty object for no params", () => {
    expect(validateRecordingsSearch({})).toEqual({});
  });

  it("keeps a non-empty search string", () => {
    expect(validateRecordingsSearch({ q: "pick" })).toEqual({ q: "pick" });
  });

  it("drops an empty search string to keep the URL clean", () => {
    expect(validateRecordingsSearch({ q: "" })).toEqual({});
  });

  it('keeps task="" (the "no task" filter)', () => {
    expect(validateRecordingsSearch({ task: "" })).toEqual({ task: "" });
  });

  it("keeps a named task filter", () => {
    expect(validateRecordingsSearch({ task: "place" })).toEqual({ task: "place" });
  });

  it("ignores non-string values", () => {
    expect(validateRecordingsSearch({ q: 5, task: true, extra: {} })).toEqual({});
  });
});
