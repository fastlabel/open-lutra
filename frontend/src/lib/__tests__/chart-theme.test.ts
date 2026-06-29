import { afterEach, describe, expect, it, vi } from "vitest";
import { getChartAxisColors } from "../chart-theme";

describe("getChartAxisColors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("falls back to default colors when the theme variables are unset", () => {
    // jsdom returns empty strings for unset custom properties.
    expect(getChartAxisColors()).toEqual({ axis: "#999", grid: "#333" });
  });

  it("reads and trims the theme variables when present", () => {
    vi.stubGlobal("getComputedStyle", () => ({
      getPropertyValue: (name: string) => (name === "--muted-foreground" ? "  #111  " : "  #222  "),
    }));
    expect(getChartAxisColors()).toEqual({ axis: "#111", grid: "#222" });
  });
});
