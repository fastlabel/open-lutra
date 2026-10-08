/** Expanded topic details: timing and loss-event list. */

import { Timer } from "lucide-react";
import type { LossEvent, TopicQuality } from "@/api/generated/schemas";
import { formatDuration } from "@/lib/format";

export function TopicDetails({
  topic,
  recordingDuration,
  lossExpanded = true,
  onLossClick,
  onLossHover,
  onLossLeave,
}: {
  topic: TopicQuality;
  recordingDuration: number;
  /** Whether to show the loss-event list. Toggled by the chevron (TopicMetrics). */
  lossExpanded?: boolean;
  onLossClick?: (topicName: string, loss: LossEvent) => void;
  onLossHover?: (topicName: string, loss: LossEvent) => void;
  onLossLeave?: () => void;
}) {
  const hasDelay = topic.start_delay_sec > 0.1;
  const hasEarlyEnd = topic.end_early_sec > 0.1;
  const showLossEvents = lossExpanded && topic.loss_events.length > 0;

  if (!hasDelay && !hasEarlyEnd && !showLossEvents) {
    return null;
  }

  return (
    <div className="px-3 pb-2 pl-9 text-xs text-muted-foreground space-y-1.5">
      {/* Start delay / early end */}
      {(hasDelay || hasEarlyEnd) && (
        <div className="flex items-center gap-1.5">
          <Timer size={11} className="shrink-0 text-muted-foreground" />
          {hasDelay && (
            <span className="text-blue-600 dark:text-blue-400">Start +{topic.start_delay_sec.toFixed(2)}s</span>
          )}
          {hasEarlyEnd && (
            <span className="text-amber-600 dark:text-amber-400">End -{topic.end_early_sec.toFixed(2)}s</span>
          )}
          <span className="text-muted-foreground">/ {formatDuration(recordingDuration)}</span>
        </div>
      )}

      {/* Loss-event list (color-coded by severity) */}
      {showLossEvents && (
        <div>
          {topic.loss_events.map((le, i, arr) => {
            const colorClass =
              le.severity === "major" ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400";
            return (
              <div
                key={le.timestamp_sec}
                className={`flex gap-2 py-0.5 ${onLossClick ? "cursor-pointer hover:text-foreground transition-colors" : ""}`}
                onClick={onLossClick ? () => onLossClick(topic.name, le) : undefined}
                onMouseEnter={onLossHover ? () => onLossHover(topic.name, le) : undefined}
                onMouseLeave={onLossLeave}
              >
                <span className="text-muted-foreground">{i < arr.length - 1 ? "├" : "└"}</span>
                <span>{formatDuration(le.timestamp_sec)}</span>
                <span className={colorClass}>
                  {le.duration_sec.toFixed(3)}s ({le.lost_count}f)
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
