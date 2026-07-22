import { describe, expect, it } from "vitest";
import { matchesPattern } from "../metadata-field";

describe("matchesPattern", () => {
  it("treats an empty value as valid", () => {
    expect(matchesPattern("^[0-9]+$", "")).toBe(true);
  });

  it("treats an absent pattern as valid", () => {
    expect(matchesPattern(null, "abc")).toBe(true);
    expect(matchesPattern(undefined, "abc")).toBe(true);
  });

  it("validates a value against the pattern", () => {
    expect(matchesPattern("^[0-9]+$", "007")).toBe(true);
    expect(matchesPattern("^[0-9]+$", "12a")).toBe(false);
  });

  it("treats a malformed pattern as valid (does not trap the operator)", () => {
    expect(matchesPattern("[unclosed", "anything")).toBe(true);
  });
});
