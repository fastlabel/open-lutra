/** Store for the color theme.
 *
 * The operator's choice from the header toggle wins over `default_color_mode` from the recording
 * config, which wins over dark. The `dark` class on <html> is updated synchronously here so canvas
 * charts that read CSS variables see the new theme when they re-render.
 */
import { create } from "zustand";
import { devtools } from "zustand/middleware";

export type Theme = "dark" | "light";

interface ThemeStore {
  /** Theme picked with the header toggle; null until the operator picks one. */
  chosen: Theme | null;
  /** `default_color_mode` from /api/config. */
  configDefault: Theme | null;

  toggleTheme: () => void;
  setConfigDefault: (theme: Theme) => void;
}

export const selectTheme = (s: Pick<ThemeStore, "chosen" | "configDefault">): Theme =>
  s.chosen ?? s.configDefault ?? "dark";

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export const useThemeStore = create<ThemeStore>()(
  devtools(
    (set, get) => ({
      chosen: null,
      configDefault: null,

      toggleTheme: () => {
        const chosen = selectTheme(get()) === "dark" ? "light" : "dark";
        applyTheme(chosen);
        set({ chosen }, false, "toggleTheme");
      },
      setConfigDefault: (configDefault) => {
        applyTheme(selectTheme({ ...get(), configDefault }));
        set({ configDefault }, false, "setConfigDefault");
      },
    }),
    { name: "ThemeStore" },
  ),
);
