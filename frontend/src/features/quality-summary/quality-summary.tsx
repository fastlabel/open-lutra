/** Quality Summary panel: fetches and displays the quality report (a static aggregate view). */

import { Clock, HardDrive, Layers, Loader2, Radio } from "lucide-react";
import { useEffect } from "react";
import type { LossEvent, QualityResponse } from "@/api/generated/schemas";
import { InfoTip } from "@/components/ui/info-tip";
import { useQualityReport, useStartQualityAnalysis } from "@/hooks/use-api";
import { formatDuration, formatSize } from "@/lib/format";
import { sortTopicsByCategory } from "@/lib/topic-sort";
import { TopicQualityRow } from "./ui/topic-quality-row";

/** Message shown when the quality report cannot be displayed. Not called when ready with a report. */
function StatusMessage({
  selectedFolder,
  data,
  isLoading,
}: {
  selectedFolder: string | null;
  data: QualityResponse | undefined;
  isLoading: boolean;
}) {
  if (!selectedFolder) {
    return <p className="p-3 text-center text-sm text-muted-foreground">Select an .mcap file</p>;
  }
  if (isLoading || data?.status === "analyzing") {
    return (
      <div className="flex items-center gap-2 px-3 py-6 justify-center text-xs text-muted-foreground">
        <Loader2 size={14} className="animate-spin" />
        <span>Analyzing quality...</span>
      </div>
    );
  }
  if (data?.status === "error") {
    return <p className="px-3 py-3 text-xs text-red-400/80">Analysis error: {data.error}</p>;
  }
  if (data?.status === "not_found") {
    return (
      <p className="px-3 py-3 text-xs text-muted-foreground">
        No quality report yet (you can run analysis from the MCAP detail page)
      </p>
    );
  }
  return <p className="px-3 py-3 text-xs text-muted-foreground">No quality report available</p>;
}

export function QualitySummary({
  selectedFolder,
  selectedTopic,
  forceExpanded,
  triggerAnalysis = false,
  onTopicClick,
  onLossClick,
  onLossHover,
  onLossLeave,
}: {
  selectedFolder: string | null;
  selectedTopic?: string | null;
  forceExpanded?: boolean;
  /** When true, trigger quality analysis if one hasn't been generated yet.
   *
   * Pass true only where the user explicitly opens this view (e.g. MCAP detail page).
   * For the recordings-list right panel etc., leave it false (default).
   */
  triggerAnalysis?: boolean;
  onTopicClick?: (topicName: string) => void;
  onLossClick?: (topicName: string, loss: LossEvent) => void;
  onLossHover?: (topicName: string, loss: LossEvent) => void;
  onLossLeave?: () => void;
}) {
  // --- Server state ---
  const { data, isLoading } = useQualityReport(selectedFolder);
  // Destructure mutate / isPending. Putting the whole useMutation return value into deps would
  // re-fire useEffect on reference changes; mutate is returned by react-query with a stable reference.
  const { mutate: startAnalysis, isPending: isStartingAnalysis } = useStartQualityAnalysis();

  // --- Side effects ---
  useEffect(() => {
    if (triggerAnalysis && selectedFolder && data?.status === "not_found" && !isStartingAnalysis) {
      startAnalysis({ params: { path: selectedFolder } });
    }
  }, [triggerAnalysis, selectedFolder, data?.status, isStartingAnalysis, startAnalysis]);

  if (!selectedFolder || data?.status !== "ready" || !data.report) {
    return <StatusMessage selectedFolder={selectedFolder} data={data} isLoading={isLoading} />;
  }

  const { report } = data;

  return (
    <div className="space-y-3 p-3">
      {/* Summary statistics (single horizontal row; icon + value only to keep vertical height minimal) */}
      <div className="flex items-center justify-between gap-1 rounded-md bg-muted/30 px-2.5 py-1.5 text-xs">
        <div className="flex items-center gap-1" title="Duration">
          <Clock size={12} className="text-muted-foreground shrink-0" />
          <span className="font-medium tabular-nums text-foreground">{formatDuration(report.duration_sec)}</span>
        </div>
        <div className="flex items-center gap-1" title="Messages">
          <Layers size={12} className="text-muted-foreground shrink-0" />
          <span className="font-medium tabular-nums text-foreground">{report.total_messages.toLocaleString()}</span>
        </div>
        <div className="flex items-center gap-1" title="Topics">
          <Radio size={12} className="text-muted-foreground shrink-0" />
          <span className="font-medium tabular-nums text-foreground">{report.total_topics}</span>
        </div>
        <div className="flex items-center gap-1" title="Size">
          <HardDrive size={12} className="text-muted-foreground shrink-0" />
          <span className="font-medium tabular-nums text-foreground">{formatSize(report.file_size_bytes)}</span>
        </div>
      </div>

      {/* Per-topic quality */}
      <div>
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Topics</span>
          <InfoTip text="Quality status per topic. loss_rate = 1 − received / expected (against the configured expected_hz when set, otherwise the measured rate); over 2% is warning (yellow), over 5% is danger (red). minor/major are discrete dropout events detected with the IQR statistical threshold (down to a single frame)." />
        </div>
        <div className="rounded-md border border-border overflow-hidden">
          {sortTopicsByCategory(
            report.topics,
            (t) => t.name,
            (t) => t.msg_type,
          ).map((topic) => (
            <TopicQualityRow
              key={topic.name}
              topic={topic}
              recordingDuration={report.duration_sec}
              isSelected={selectedTopic === topic.name}
              forceExpanded={forceExpanded}
              onTopicClick={onTopicClick}
              onLossClick={onLossClick}
              onLossHover={onLossHover}
              onLossLeave={onLossLeave}
            />
          ))}
        </div>

        {/* Metrics legend */}
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            Hz
            <InfoTip text="Measured frequency. Derived from the median header.stamp interval; rounded to the nearest standard value (10/30/100/200Hz etc.)." />
          </span>
          <span className="flex items-center gap-1">
            loss
            <InfoTip text="loss_rate = 1 − received / (expected_hz × duration). The received-vs-expected frame deficit; expected_hz comes from the recording config when set, otherwise the measured rate." />
          </span>
          <span className="flex items-center gap-1">
            minor / major
            <InfoTip text="minor = event count of 1-2 frame losses (yellow); major = event count of 3+ consecutive frame losses (red). Major losses penalize the score by 5% per event." />
          </span>
          <span className="flex items-center gap-1">
            delay
            <InfoTip text="Delay from recording start to the first message of the topic. Shown when ≥ 0.1s. Long delays are also counted as edge loss." />
          </span>
          <span className="flex items-center gap-1">
            empty
            <InfoTip text="Number of zero-byte messages. For image topics this may indicate black or corrupted frames." />
          </span>
        </div>
      </div>
    </div>
  );
}
