import { describe, expect, it } from "vitest";
import { applyRange } from "../range-select";

const DISPLAYED = ["a", "b", "c", "d", "e"];

describe("applyRange", () => {
  it("checks every row from the anchor to the target when the anchor is checked", () => {
    expect(applyRange(new Set(["b"]), DISPLAYED, "b", "d")).toEqual(new Set(["b", "c", "d"]));
  });

  it("works upwards from the anchor too", () => {
    expect(applyRange(new Set(["d"]), DISPLAYED, "d", "a")).toEqual(new Set(["a", "b", "c", "d"]));
  });

  it("unchecks the range when the anchor is unchecked, leaving rows outside it alone", () => {
    expect(applyRange(new Set(["a", "c", "d", "e"]), DISPLAYED, "b", "d")).toEqual(new Set(["a", "e"]));
  });

  it("keeps checked folders that are not displayed", () => {
    expect(applyRange(new Set(["a", "hidden"]), DISPLAYED, "a", "b")).toEqual(new Set(["a", "b", "hidden"]));
  });

  it("does not mutate the input set", () => {
    const checked = new Set(["a"]);
    applyRange(checked, DISPLAYED, "a", "c");
    expect(checked).toEqual(new Set(["a"]));
  });

  it("returns null without an anchor", () => {
    expect(applyRange(new Set(), DISPLAYED, null, "c")).toBeNull();
  });

  it("returns null when the anchor or the target is not displayed", () => {
    expect(applyRange(new Set(["x"]), DISPLAYED, "x", "c")).toBeNull();
    expect(applyRange(new Set(["a"]), DISPLAYED, "a", "x")).toBeNull();
  });
});
