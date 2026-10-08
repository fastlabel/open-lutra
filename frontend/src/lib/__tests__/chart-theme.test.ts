import { afterEach, describe, expect, it, vi } from "vitest";
import { getChartColors } from "../chart-theme";

describe("getChartColors", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("falls back to default colors when the theme variables are unset", () => {
    // jsdom returns empty strings for unset custom properties.
    expect(getChartColors()).toEqual({ axis: "#999", grid: "#333", playhead: "#e5e5e5" });
  });

  it("reads and trims the theme variables when present", () => {
    vi.stubGlobal("getComputedStyle", () => ({
      getPropertyValue: (name: string) =>
        ({ "--muted-foreground": "  #111  ", "--border": "  #222  " })[name] ?? "  #333  ",
    }));
    expect(getChartColors()).toEqual({ axis: "#111", grid: "#222", playhead: "#333" });
  });
});
