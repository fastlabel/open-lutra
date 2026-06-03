/** Monitor tabs: switches between the Loss Rate chart (default) and Log views. */

import { Activity, PanelBottomClose, PanelBottomOpen, ScrollText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { type BottomTab, usePanelStore } from "@/stores/panel-store";
import { LogViewer } from "./log-viewer";
import { LossRateChart } from "./loss-rate-chart";

const tabs: { id: BottomTab; label: string; icon: React.ReactNode }[] = [
  { id: "loss-rate", label: "Loss Rate", icon: <Activity size={13} /> },
  { id: "log", label: "Log", icon: <ScrollText size={13} /> },
];

/** Tab header (tab buttons + minimize/restore toggle).
 *
 * Rendered alone as the minimized bar at the bottom of the screen,
 * or as the header of the full tab panel.
 */
export function MonitorTabsHeader({ placement = "in-panel" }: { placement?: "in-panel" | "bottom-bar" } = {}) {
  const activeTab = usePanelStore((s) => s.bottomTab);
  const setTab = usePanelStore((s) => s.setBottomTab);
  const minimized = usePanelStore((s) => s.bottomPaneMinimized);
  const toggleMinimized = usePanelStore((s) => s.toggleBottomPaneMinimized);

  const borderClass = placement === "bottom-bar" ? "border-t border-border" : "border-b border-border";

  return (
    <div className={`flex items-center justify-between ${borderClass}`}>
      <div className="flex items-center">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-semibold uppercase tracking-wider transition-colors ${
              !minimized && activeTab === tab.id
                ? "text-foreground border-b-2 border-foreground"
                : "text-muted-foreground hover:text-foreground/70"
            }`}
            onClick={() => {
              setTab(tab.id);
              if (minimized) usePanelStore.getState().setBottomPaneMinimized(false);
            }}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" className="h-6 w-6 mr-1" onClick={toggleMinimized}>
            {minimized ? <PanelBottomOpen size={13} /> : <PanelBottomClose size={13} />}
          </Button>
        </TooltipTrigger>
        <TooltipContent side="top">{minimized ? "Restore panel" : "Minimize to bottom"}</TooltipContent>
      </Tooltip>
    </div>
  );
}

export function MonitorTabs() {
  const activeTab = usePanelStore((state) => state.bottomTab);

  return (
    <div className="flex h-full flex-col bg-background">
      <MonitorTabsHeader />
      <div className="flex-1 overflow-hidden">{activeTab === "loss-rate" ? <LossRateChart /> : <LogViewer />}</div>
    </div>
  );
}
