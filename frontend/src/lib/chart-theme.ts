/** Resolve colors for canvas charts (uPlot, etc.) from theme CSS variables.
 *
 * Returns `--muted-foreground` for axis lines / tick labels (matching other muted text),
 * `--border` (the subtle divider color) for grid lines, and `--foreground` for the playhead.
 */
import { useMemo } from "react";
import { useThemeStore } from "@/stores/theme-store";

export interface ChartColors {
  axis: string;
  grid: string;
  playhead: string;
}

export function getChartColors(): ChartColors {
  const style = getComputedStyle(document.documentElement);
  return {
    axis: style.getPropertyValue("--muted-foreground").trim() || "#999",
    grid: style.getPropertyValue("--border").trim() || "#333",
    playhead: style.getPropertyValue("--foreground").trim() || "#e5e5e5",
  };
}

/** Chart colors for the current theme; a new object on each theme switch, so charts can rebuild on it. */
export function useChartColors(): ChartColors {
  const theme = useThemeStore((s) => s.theme);
  // biome-ignore lint/correctness/useExhaustiveDependencies: the CSS variables change with the theme
  return useMemo(getChartColors, [theme]);
}
