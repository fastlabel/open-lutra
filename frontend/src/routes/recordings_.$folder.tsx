/** MCAP detail page: quality assessment (left) + tabbed analytics / validation (right). */

import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { useCallback, useEffect } from "react";
import { Group, Panel } from "react-resizable-panels";
import type { LossEvent } from "@/api/generated/schemas";
import { ResizeHandleH } from "@/components/ui/resize-handle";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { QualitySummary } from "@/features/quality-summary";
import { QualityTimeline, useQualityTimelineStore } from "@/features/quality-timeline";
import { UploadButton } from "@/features/upload";
import { ValidationSummary } from "@/features/validation";

/** Compute the display range for a loss event (minimum 0.5 seconds). */
function lossViewRange(loss: LossEvent, durationSec: number): { from: number; to: number } {
  const lossEnd = loss.timestamp_sec + loss.duration_sec;
  const span = Math.max(0.5, loss.duration_sec * 1.2);
  const from = Math.max(0, loss.timestamp_sec - span * 0.1);
  const to = Math.min(durationSec, from + span);
  return { from, to: Math.max(to, lossEnd) };
}

function McapDetailPage() {
  // --- Routing ---
  const { folder } = Route.useParams();
  const folderPath = decodeURIComponent(folder);

  // --- Side effects ---
  // Reset the store on unmount (resets viewRange etc. when leaving the page).
  const reset = useQualityTimelineStore((s) => s.reset);
  useEffect(() => {
    return () => reset();
  }, [reset]);

  // --- Event handlers (callbacks passed to JSX) ---
  const selectedTopic = useQualityTimelineStore((s) => s.selectedTopic);
  const setSelectedTopic = useQualityTimelineStore((s) => s.setSelectedTopic);
  const setViewRange = useQualityTimelineStore((s) => s.setViewRange);
  const setPlayheadSec = useQualityTimelineStore((s) => s.setPlayheadSec);
  const durationSec = useQualityTimelineStore((s) => s.durationSec);
  const setHoveredLossEvent = useQualityTimelineStore((s) => s.setHoveredLossEvent);

  // Topic click → toggle selection.
  const handleTopicClick = useCallback(
    (topicName: string) => {
      setSelectedTopic(selectedTopic === topicName ? null : topicName);
    },
    [selectedTopic, setSelectedTopic],
  );

  // Loss event click → select the topic, zoom the range, and move the playhead.
  const handleLossClick = useCallback(
    (topicName: string, loss: LossEvent) => {
      setSelectedTopic(topicName);
      setViewRange(lossViewRange(loss, durationSec));
      setPlayheadSec(loss.timestamp_sec);
    },
    [durationSec, setSelectedTopic, setViewRange, setPlayheadSec],
  );

  // Loss event hover → highlight the corresponding gap in the timeline heatmap.
  const handleLossHover = useCallback(
    (topicName: string, loss: LossEvent) => {
      setHoveredLossEvent({ topicName, timestampSec: loss.timestamp_sec });
    },
    [setHoveredLossEvent],
  );
  const handleLossLeave = useCallback(() => {
    setHoveredLossEvent(null);
  }, [setHoveredLossEvent]);

  return (
    <Tabs defaultValue="quality" className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-2">
        <Link
          to="/recordings"
          className="flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <ArrowLeft size={16} />
        </Link>
        <span className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          {folderPath.split("/").pop() ?? folder}
        </span>
        <UploadButton folderPath={folderPath} />
        <TabsList className="ml-auto -my-2 self-stretch">
          <TabsTrigger value="quality">Quality Analytics</TabsTrigger>
          <TabsTrigger value="validation">Validation</TabsTrigger>
        </TabsList>
      </div>

      {/* Main content: left and right panels */}
      <div className="flex-1 overflow-hidden">
        <Group orientation="horizontal" className="h-full">
          {/* Left panel: quality summary */}
          <Panel defaultSize="33%" minSize="15%" maxSize="40%" id="detail-left">
            <ScrollArea className="h-full border-r border-border">
              <QualitySummary
                selectedFolder={folderPath}
                selectedTopic={selectedTopic}
                forceExpanded
                triggerAnalysis
                onTopicClick={handleTopicClick}
                onLossClick={handleLossClick}
                onLossHover={handleLossHover}
                onLossLeave={handleLossLeave}
              />
            </ScrollArea>
          </Panel>

          <ResizeHandleH />

          {/* Right panel: tabbed analytics / validation */}
          <Panel minSize="40%" id="detail-right">
            <TabsContent value="quality" className="h-full overflow-hidden">
              <QualityTimeline selectedFolder={folderPath} />
            </TabsContent>
            <TabsContent value="validation" className="h-full overflow-hidden">
              <ScrollArea className="h-full">
                <ValidationSummary selectedFolder={folderPath} triggerAnalysis />
              </ScrollArea>
            </TabsContent>
          </Panel>
        </Group>
      </div>
    </Tabs>
  );
}

export const Route = createFileRoute("/recordings_/$folder")({
  component: McapDetailPage,
});
