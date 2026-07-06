/** Topic metrics row: type, message count, loss rate, delay, empty, expand toggle. */

import { ChevronDown, ChevronRight } from "lucide-react";
import type { MouseEvent } from "react";
import type { TopicQuality } from "@/api/generated/schemas";
import { formatSize } from "@/lib/format";
import { shortMsgType } from "../quality-utils";

export function TopicMetrics({
  topic,
  expanded,
  hasDetails,
  onChevronClick,
}: {
  topic: TopicQuality;
  expanded: boolean;
  hasDetails: boolean;
  /** Chevron click handler. When provided, stops the row click and toggles independently. */
  onChevronClick?: (e: MouseEvent) => void;
}) {
  const { minor_loss_count, major_loss_count, loss_rate, message_count, start_delay_sec, msg_type } = topic;
  const { zero_size_count, avg_bytes } = topic.size_stats;

  // Count-based loss rate: received frames vs the expected count (uses the configured
  // expected_hz when set). Colored by the same 2% / 5% warn/danger thresholds.
  const missClass = loss_rate > 0.05 ? "text-red-400" : loss_rate > 0.02 ? "text-amber-400" : "";
  const chevronIcon = expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />;

  return (
    <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground flex-wrap">
      <span>{shortMsgType(msg_type)}</span>
      <span>Size: {formatSize(avg_bytes)} avg</span>
      <span>{message_count.toLocaleString()} msgs</span>
      <span className={missClass}>{(loss_rate * 100).toFixed(2)}% loss</span>
      {start_delay_sec > 0.1 && (
        <span className="rounded bg-blue-500/15 px-1 py-0 text-[10px] text-blue-400">
          +{start_delay_sec.toFixed(1)}s delay
        </span>
      )}
      {zero_size_count > 0 && (
        <span className="rounded bg-red-500/15 px-1 py-0 text-[10px] text-red-400">{zero_size_count} empty</span>
      )}
      {hasDetails &&
        (onChevronClick ? (
          <button
            type="button"
            onClick={onChevronClick}
            aria-label={expanded ? "Collapse" : "Expand"}
            className="ml-auto flex items-center gap-1 shrink-0 text-muted-foreground hover:text-foreground transition-colors"
          >
            {minor_loss_count > 0 && <span className="text-amber-400">{minor_loss_count} minor</span>}
            {major_loss_count > 0 && <span className="text-red-400">{major_loss_count} major</span>}
            {chevronIcon}
          </button>
        ) : (
          <span className="ml-auto flex items-center gap-1 shrink-0">
            {minor_loss_count > 0 && <span className="text-amber-400">{minor_loss_count} minor</span>}
            {major_loss_count > 0 && <span className="text-red-400">{major_loss_count} major</span>}
            {chevronIcon}
          </span>
        ))}
    </div>
  );
}
