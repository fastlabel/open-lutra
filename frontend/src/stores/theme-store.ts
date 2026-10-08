/** Store for the color theme, persisted to localStorage.
 *
 * The `dark` class on <html> is set by the inline script in index.html before the first paint,
 * and toggled here synchronously so canvas charts that read CSS variables see the new theme
 * when they re-render.
 */
import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

export type Theme = "dark" | "light";

interface ThemeStore {
  theme: Theme;
  toggleTheme: () => void;
}

export const useThemeStore = create<ThemeStore>()(
  devtools(
    persist(
      (set, get) => ({
        theme: "dark",

        toggleTheme: () => {
          const theme = get().theme === "dark" ? "light" : "dark";
          document.documentElement.classList.toggle("dark", theme === "dark");
          set({ theme }, false, "toggleTheme");
        },
      }),
      {
        name: "app-theme",
        partialize: (state) => ({ theme: state.theme }),
      },
    ),
    { name: "ThemeStore" },
  ),
);
