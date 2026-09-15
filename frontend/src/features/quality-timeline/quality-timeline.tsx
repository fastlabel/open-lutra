/** Right panel body of the MCAP detail page.
 *
 * Composed of a scrollable area (Timeline + Adaptive Detail + Preview) and
 * a fixed Timeline Controller.
 *
 * Layout order:
 *   1. Timeline Heatmap     (always visible)
 *   2. Missing Rate / Ticks (always visible)
 *   3. Preview Panel        (collapsible, collapsed by default)
 *   4. Timeline Controller  (fixed at the bottom)
 */

import { Loader2 } from "lucide-react";
import { useEffect } from "react";
import { useStartTimelineAnalysis } from "@/hooks/use-api";
import { useQualityTimelineStore } from "./store";
import { AdaptiveDetail } from "./ui/adaptive-detail";
import { PreviewPanel } from "./ui/preview-panel";
import { TimelineController } from "./ui/timeline-controller";
import { TimelineHeatmap } from "./ui/timeline-heatmap";
import { useTimeline } from "./use-timeline";

export function QualityTimeline({ selectedFolder }: { selectedFolder: string }) {
  const { data, isLoading } = useTimeline(selectedFolder);
  const setDurationSec = useQualityTimelineStore((s) => s.setDurationSec);
  const { mutate: startTimeline, isPending: isStartingTimeline } = useStartTimelineAnalysis();

  useEffect(() => {
    if (data?.status === "ready" && data.data) {
      setDurationSec(data.data.duration_sec);
    }
  }, [data, setDurationSec]);

  useEffect(() => {
    if (data?.status === "not_found" && !isStartingTimeline) {
      startTimeline({ params: { path: selectedFolder } });
    }
  }, [data?.status, selectedFolder, isStartingTimeline, startTimeline]);

  if (isLoading || data?.status === "analyzing") {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 size={14} className="animate-spin" />
          <span>Generating timeline data...</span>
        </div>
      </div>
    );
  }

  if (data?.status === "error") {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-xs text-red-400/80">Error: {data.error}</p>
      </div>
    );
  }

  if (!data?.data || data.status !== "ready") {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-xs text-muted-foreground">No timeline data available</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Scrollable area */}
      <div className="flex-1 overflow-auto p-3 space-y-4">
        <TimelineHeatmap data={data.data} />
        <AdaptiveDetail data={data.data} selectedFolder={selectedFolder} />
        <PreviewPanel selectedFolder={selectedFolder} />
      </div>

      {/* Fixed controller */}
      <TimelineController data={data.data} />
    </div>
  );
}
