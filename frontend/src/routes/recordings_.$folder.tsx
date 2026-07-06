/** MCAP detail page: quality assessment (left) + tabbed analytics / validation (right). */

import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect } from "react";
import { Group, Panel } from "react-resizable-panels";
import type { LossEvent } from "@/api/generated/schemas";
import { ResizeHandleH } from "@/components/ui/resize-handle";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { QualitySummary } from "@/features/quality-summary";
import { QualityTimeline, useQualityTimelineStore } from "@/features/quality-timeline";
import { useRecordingNeighbors, validateRecordingsSearch } from "@/features/recordings-table";
import { UploadButton } from "@/features/upload";
import { ValidationSummary } from "@/features/validation";

// Shared icon-button base for the header pager (matches the back-to-list link).
const PAGER_BTN = "flex h-7 w-7 items-center justify-center rounded transition-colors";

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
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const folderPath = decodeURIComponent(folder);

  // --- Server state (derived) ---
  // Previous/next recording within the same filtered view the user came from.
  const { prev, next, index, total, currentExists, isLoaded } = useRecordingNeighbors(
    folderPath,
    search.q ?? "",
    search.task ?? null,
  );

  // --- Side effects ---
  // Reset the store on unmount (resets viewRange etc. when leaving the page).
  const reset = useQualityTimelineStore((s) => s.reset);
  useEffect(() => {
    return () => reset();
  }, [reset]);

  // When the viewed recording no longer exists (e.g. deleted while open), return to the list.
  useEffect(() => {
    if (isLoaded && !currentExists) navigate({ to: "/recordings", search });
  }, [isLoaded, currentExists, navigate, search]);

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
          search={search}
          className={`${PAGER_BTN} text-muted-foreground hover:bg-muted hover:text-foreground`}
          title="Back to recordings"
        >
          <ArrowLeft size={16} />
        </Link>

        {/* Previous / next recording pager */}
        <div className="flex items-center gap-0.5">
          {prev ? (
            <Link
              to="/recordings/$folder"
              params={{ folder: encodeURIComponent(prev.path) }}
              search={search}
              className={`${PAGER_BTN} text-muted-foreground hover:bg-muted hover:text-foreground`}
              title={`Previous: ${prev.task_name ?? prev.name}`}
            >
              <ChevronLeft size={16} />
            </Link>
          ) : (
            <button
              type="button"
              disabled
              className={`${PAGER_BTN} cursor-not-allowed text-muted-foreground opacity-30`}
              title="No previous recording"
            >
              <ChevronLeft size={16} />
            </button>
          )}
          {index >= 0 && (
            <span className="px-1 text-sm text-muted-foreground tabular-nums">
              {index + 1} / {total}
            </span>
          )}
          {next ? (
            <Link
              to="/recordings/$folder"
              params={{ folder: encodeURIComponent(next.path) }}
              search={search}
              className={`${PAGER_BTN} text-muted-foreground hover:bg-muted hover:text-foreground`}
              title={`Next: ${next.task_name ?? next.name}`}
            >
              <ChevronRight size={16} />
            </Link>
          ) : (
            <button
              type="button"
              disabled
              className={`${PAGER_BTN} cursor-not-allowed text-muted-foreground opacity-30`}
              title="No next recording"
            >
              <ChevronRight size={16} />
            </button>
          )}
        </div>

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
  validateSearch: validateRecordingsSearch,
  component: McapDetailPage,
});
