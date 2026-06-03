/** PREVIEW panel: displays previewed topic details in a grid.
 *
 * Shows a placeholder prompting recording when nothing is previewed.
 * Auto-switches between 1 / 1x2 / 2x2 grids based on the number of tiles.
 */

import { Video } from "lucide-react";
import type { TopicInfo } from "@/api/generated/schemas";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useRecordingStore } from "@/features/recording";
import { TopicPreviewTile } from "./topic-preview-tile";

function PreviewHeader({ count }: { count: number }) {
  const stopLiveMonitor = useRecordingStore((s) => s.stopLiveMonitorDuringRecording);
  const setStopLiveMonitor = useRecordingStore((s) => s.setStopLiveMonitor);

  return (
    <div className="flex items-center justify-between border-b border-border px-3 py-2">
      <div className="flex items-center gap-6">
        <span className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Live Preview</span>
        <div className="flex items-center gap-1.5">
          <Label htmlFor="stop-live-monitor" className="text-[13px] text-muted-foreground cursor-pointer">
            Stop while recording
          </Label>
          <Switch id="stop-live-monitor" checked={stopLiveMonitor} onCheckedChange={setStopLiveMonitor} />
        </div>
      </div>
      {count > 0 && <span className="text-xs text-muted-foreground">{count}/4</span>}
    </div>
  );
}

function PreviewEmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-muted-foreground">
      <Video size={32} strokeWidth={1.5} className="opacity-50" />
      <div className="space-y-1">
        <p className="text-[13px]">Select a topic to see its preview</p>
        <p className="text-[13px] text-muted-foreground/70">Click to show up to 4 at the same time</p>
      </div>
    </div>
  );
}

/** Returns the grid class for the given tile count.
 *
 * 1: full / 2: two columns side-by-side / 3-4: 2x2 (when 3, the bottom-right cell is empty)
 */
function gridClassFor(count: number): string {
  if (count <= 1) return "grid h-full grid-cols-1 grid-rows-1 gap-2 p-2";
  if (count === 2) return "grid h-full grid-cols-2 grid-rows-1 gap-2 p-2";
  return "grid h-full grid-cols-2 grid-rows-2 gap-2 p-2";
}

export function PreviewPane({ previewedTopics }: { previewedTopics: TopicInfo[] }) {
  return (
    <div className="flex h-full flex-col bg-background">
      <PreviewHeader count={previewedTopics.length} />
      <div className="min-h-0 flex-1">
        {previewedTopics.length === 0 ? (
          <PreviewEmptyState />
        ) : (
          <div className={gridClassFor(previewedTopics.length)}>
            {previewedTopics.map((topic) => (
              <TopicPreviewTile key={topic.name} topic={topic} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
