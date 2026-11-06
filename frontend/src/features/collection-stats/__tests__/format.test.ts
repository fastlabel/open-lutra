import { describe, expect, it } from "vitest";
import { formatCollectedDuration, formatEpisodes } from "../format";

describe("formatCollectedDuration", () => {
  it.each([
    [0, "0s"],
    [16.1, "16s"],
    [59.9, "59s"],
    [60, "1m 00s"],
    [32 * 60 + 10, "32m 10s"],
    [3599, "59m 59s"],
    [3600, "1h 00m"],
    [3600 + 5 * 60 + 59, "1h 05m"],
    [12 * 3600 + 30 * 60, "12h 30m"],
  ])("formats %f seconds as %s", (sec, expected) => {
    expect(formatCollectedDuration(sec)).toBe(expected);
  });
});

describe("formatEpisodes", () => {
  it.each([
    [0, "0 episodes"],
    [1, "1 episode"],
    [2, "2 episodes"],
  ])("formats %i as %s", (count, expected) => {
    expect(formatEpisodes(count)).toBe(expected);
  });
});
