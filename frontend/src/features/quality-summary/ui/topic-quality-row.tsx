/** Topic-quality row: per-topic status, metrics, and expanded details. */

import { type MouseEvent, useEffect, useRef, useState } from "react";
import type { LossEvent, TopicQuality } from "@/api/generated/schemas";
import { TopicDetails } from "./topic-details";
import { TopicMetrics } from "./topic-metrics";

export function TopicQualityRow({
  topic,
  recordingDuration,
  isSelected,
  forceExpanded,
  onTopicClick,
  onLossClick,
  onLossHover,
  onLossLeave,
}: {
  topic: TopicQuality;
  recordingDuration: number;
  isSelected?: boolean;
  forceExpanded?: boolean;
  onTopicClick?: (topicName: string) => void;
  onLossClick?: (topicName: string, loss: LossEvent) => void;
  onLossHover?: (topicName: string, loss: LossEvent) => void;
  onLossLeave?: () => void;
}) {
  const [localExpanded, setLocalExpanded] = useState(false);
  // State for collapsing just the loss-event list while the row body is always expanded via forceExpanded
  const [lossExpanded, setLossExpanded] = useState(false);
  const rowRef = useRef<HTMLDivElement>(null);
  const hasDetails = topic.loss_events.length > 0;
  const expanded = forceExpanded ?? localExpanded;
  // What the chevron reflects: loss-list collapse during forceExpanded, otherwise row expansion
  const chevronExpanded = forceExpanded ? lossExpanded : expanded;

  useEffect(() => {
    if (isSelected && rowRef.current) {
      rowRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [isSelected]);

  const handleClick = () => {
    if (onTopicClick) {
      onTopicClick(topic.name);
    } else if (hasDetails) {
      setLocalExpanded(!localExpanded);
    }
  };

  // Toggle the chevron independently of row clicks (topic selection)
  const handleChevronClick = (e: MouseEvent) => {
    e.stopPropagation();
    if (forceExpanded) {
      setLossExpanded(!lossExpanded);
    } else {
      setLocalExpanded(!localExpanded);
    }
  };

  return (
    <div
      ref={rowRef}
      className={`border-b border-border/50 last:border-b-0 ${
        isSelected ? "relative bg-cyan-500/10 shadow-[inset_3px_0_0_0_rgb(34,211,238)]" : ""
      }`}
    >
      <div
        className={`flex items-start gap-2 px-3 py-2 ${hasDetails || onTopicClick ? "cursor-pointer hover:bg-muted/20" : ""}`}
        onClick={handleClick}
      >
        {/* Reserved slot for future per-topic validation result icon. */}
        <div className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          {/* Line 1: topic name + frequency */}
          <div className="flex items-center gap-2">
            <span className="truncate text-sm text-foreground" title={topic.name}>
              {topic.name}
            </span>
            <span className="ml-auto shrink-0 text-xs text-muted-foreground">
              {topic.actual_frequency_hz > 0 ? `${topic.actual_frequency_hz}Hz` : "-"}
            </span>
          </div>
          {/* Line 2: metrics + tags */}
          <TopicMetrics
            topic={topic}
            expanded={chevronExpanded}
            hasDetails={hasDetails}
            onChevronClick={hasDetails ? handleChevronClick : undefined}
          />
        </div>
      </div>

      {expanded && (
        <TopicDetails
          topic={topic}
          recordingDuration={recordingDuration}
          lossExpanded={forceExpanded ? lossExpanded : true}
          onLossClick={onLossClick}
          onLossHover={onLossHover}
          onLossLeave={onLossLeave}
        />
      )}
    </div>
  );
}
