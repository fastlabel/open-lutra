/** Row component for the topic list (single-line layout). */

import { memo } from "react";
import type { TopicInfo } from "@/api/generated/schemas";
import { Checkbox } from "@/components/ui/checkbox";
import { useIsRecording, useUpdateSubscriptions } from "@/hooks/use-api";
import { useLiveTopicsStore } from "../store";

/** Dot colors for each status */
const statusDotColors: Record<string, string> = {
  ok: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-red-500",
  inactive: "bg-muted-foreground/30",
};

/** Build the Hz display */
function HzLabel({ topic }: { topic: TopicInfo }) {
  const { actual_hz, status, baseline_hz } = topic;

  if (status === "inactive") {
    return <span>idle</span>;
  }

  if (status === "danger") {
    return <span className="text-red-400">stalled</span>;
  }

  // Baseline not yet established (still learning)
  if (baseline_hz == null && actual_hz === 0) {
    return <span>learning</span>;
  }

  // Baseline established: "88/100Hz"
  if (baseline_hz != null) {
    return (
      <span>
        {actual_hz.toFixed(0)}
        <span className="text-muted-foreground">/{baseline_hz}Hz</span>
      </span>
    );
  }

  // Baseline not yet established, but data is arriving
  return <span>{actual_hz.toFixed(0)}Hz</span>;
}

/** Memoized: SSE writes go through TanStack Query structural sharing, so the
 * `topic` reference only changes for rows whose values actually changed —
 * memo keeps the other ~100 rows from re-rendering on every 1Hz tick. */
export const TopicItem = memo(function TopicItem({
  topic,
  isMissing = false,
}: {
  topic: TopicInfo;
  isMissing?: boolean;
}) {
  const isSelected = useLiveTopicsStore((s) => s.selectedTopics.has(topic.name));
  const isPreviewed = useLiveTopicsStore((s) => s.previewedTopics.includes(topic.name));
  const isLive = useLiveTopicsStore((s) => s.isLive);
  const toggleTopic = useLiveTopicsStore((s) => s.toggleTopic);
  const togglePreviewedTopic = useLiveTopicsStore((s) => s.togglePreviewedTopic);
  const isRecording = useIsRecording();
  const updateSubs = useUpdateSubscriptions();

  const handleToggle = () => {
    toggleTopic(topic.name);
    const updated = useLiveTopicsStore.getState().selectedTopics;
    updateSubs.mutate({ data: { topics: [...updated] } });
  };

  const { loss_rate, status, baseline_hz, baseline_fixed } = topic;
  const showAuto = baseline_hz != null && !baseline_fixed;

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 ${isLive && !isPreviewed ? "opacity-40 cursor-not-allowed" : "hover:bg-muted/50 cursor-pointer"} ${isPreviewed ? "bg-muted/40" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        if (!isLive) togglePreviewedTopic(topic.name);
      }}
    >
      <Checkbox
        checked={isSelected}
        onCheckedChange={handleToggle}
        disabled={isRecording}
        className="h-4 w-4 shrink-0"
        onClick={(e) => e.stopPropagation()}
      />
      {isMissing ? (
        // YAML default topic that has not yet appeared in the SSE stream — drawn as a hollow gray ring
        // to distinguish it from backend-known topics (which use the solid status dot).
        <span className="h-2.5 w-2.5 shrink-0 rounded-full border border-muted-foreground/60 bg-transparent" />
      ) : (
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusDotColors[status] ?? statusDotColors.inactive}`} />
      )}
      <p className="min-w-0 flex-1 truncate font-mono text-sm text-foreground" title={topic.name}>
        {topic.name}
      </p>
      <div className="flex items-center gap-1.5 shrink-0 text-xs text-muted-foreground">
        {loss_rate > 0.02 && (
          <span className={loss_rate > 0.05 ? "text-red-400" : "text-amber-400"}>
            {(loss_rate * 100).toFixed(1)}% loss
          </span>
        )}
        {showAuto && <span className="text-blue-400">auto</span>}
        <HzLabel topic={topic} />
      </div>
    </div>
  );
});
