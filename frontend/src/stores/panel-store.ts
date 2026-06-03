/** Store that manages panel state. */
import { create } from "zustand";
import { devtools } from "zustand/middleware";

export type BottomTab = "loss-rate" | "log";

interface PanelStore {
  /** Active tab of the bottom panel. */
  bottomTab: BottomTab;
  /** Whether the bottom panel (Loss Rate / Log) is minimized to the bottom of the screen. */
  bottomPaneMinimized: boolean;
  /** Visibility of the TanStack Query DevTools (development only). */
  showQueryDevtools: boolean;
  /** Open/closed state of the recording page's left sidebar (Topics). */
  topicsSidebarOpen: boolean;

  setBottomTab: (tab: BottomTab) => void;
  setBottomPaneMinimized: (minimized: boolean) => void;
  toggleBottomPaneMinimized: () => void;
  toggleQueryDevtools: () => void;
  toggleTopicsSidebar: () => void;
}

export const usePanelStore = create<PanelStore>()(
  devtools(
    (set) => ({
      bottomTab: "loss-rate",
      bottomPaneMinimized: false,
      showQueryDevtools: false,
      topicsSidebarOpen: true,

      setBottomTab: (tab) => set({ bottomTab: tab }, false, "setBottomTab"),
      setBottomPaneMinimized: (minimized) => set({ bottomPaneMinimized: minimized }, false, "setBottomPaneMinimized"),
      toggleBottomPaneMinimized: () =>
        set((state) => ({ bottomPaneMinimized: !state.bottomPaneMinimized }), false, "toggleBottomPaneMinimized"),
      toggleQueryDevtools: () =>
        set((state) => ({ showQueryDevtools: !state.showQueryDevtools }), false, "toggleQueryDevtools"),
      toggleTopicsSidebar: () =>
        set((state) => ({ topicsSidebarOpen: !state.topicsSidebarOpen }), false, "toggleTopicsSidebar"),
    }),
    { name: "PanelStore" },
  ),
);
