/** Topic detail panel: mini-dashboard for the selected topic.
 *
 * Called from PreviewPane; the body renders a quality line / image preview / detail
 * stats / latest message. For image topics the preview sits directly under the quality
 * line so the video stays visible without scrolling past the stats.
 * The panel header is assembled by the caller (PreviewPane).
 */

import { ChevronDown, ChevronRight, Circle } from "lucide-react";
import { useEffect, useState } from "react";
import type { TopicInfo } from "@/api/generated/schemas";
import { useTopicMessage } from "@/hooks/use-api";
import { useLiveTopicsStore } from "../store";

/** Whether the msg_type is an image topic. */
function isImageTopic(msgType: string): boolean {
  return msgType.includes("Image");
}

/** Quality line: rate + status + loss at a glance, shown above the preview. */
function QualityLine({ topic }: { topic: TopicInfo }) {
  // loss_rate is meaningless when the topic is stalled (backend resets it to 0)
  // or when no baseline has been established — render "--" in those cases.
  const lossUnknown = topic.status === "danger" || topic.baseline_hz == null;
  const lossColor = topic.loss_rate > 0.05 ? "text-red-400" : topic.loss_rate > 0.02 ? "text-amber-400" : "";
  const statusColor =
    topic.status === "ok"
      ? "text-emerald-400"
      : topic.status === "warning"
        ? "text-amber-400"
        : topic.status === "danger"
          ? "text-red-400"
          : "text-muted-foreground";

  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="font-mono text-sm text-foreground">{topic.actual_hz.toFixed(0)} Hz</span>
      <span className={`flex items-center gap-1 ${statusColor}`}>
        <Circle size={8} className="fill-current" />
        {topic.status}
      </span>
      <span className="text-muted-foreground">
        loss{" "}
        <span className={`font-mono ${lossUnknown ? "" : lossColor}`}>
          {lossUnknown ? "--" : `${(topic.loss_rate * 100).toFixed(1)}%`}
        </span>
      </span>
    </div>
  );
}

/** Detail stats: baseline / drop / type / QoS, shown below the preview. */
function StatsDetail({ topic }: { topic: TopicInfo }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
      <div className="text-muted-foreground">baseline</div>
      <div className="font-mono">
        {topic.baseline_hz != null ? `${topic.baseline_hz} Hz` : "--"}
        {topic.baseline_fixed ? "" : " (auto)"}
      </div>
      <div className="text-muted-foreground">drop</div>
      <div className="font-mono">{topic.drop_count}/s</div>
      <div className="text-muted-foreground">type</div>
      <div className="font-mono text-muted-foreground truncate" title={topic.msg_type}>
        {topic.msg_type.split("/").pop()}
      </div>
      <div className="text-muted-foreground">QoS</div>
      <div className="font-mono text-muted-foreground">{topic.qos_reliability}</div>
    </div>
  );
}

/** Image preview (always MJPEG. 30fps while Live, 2fps otherwise)
 *
 * The stream URL is built against `VITE_API_BASE` when set so the MJPEG connections
 * land on the backend origin directly instead of the Vite dev-server proxy. The Vite
 * proxy shares Chrome's 6-connection-per-origin budget with the SSE streams and the
 * top-level document, so routing long-lived MJPEG through it can starve POSTs and
 * page reloads. Unset in production (same-origin), so the URL stays relative.
 */
function ImagePreview({ topicName, isLive }: { topicName: string; isLive: boolean }) {
  const streamUrl = `${import.meta.env.VITE_API_BASE ?? ""}/api/topics/image/stream?topic=${encodeURIComponent(topicName)}`;

  return (
    <img
      src={streamUrl}
      alt="MJPEG preview"
      className={`w-full rounded border ${isLive ? "border-red-500/50" : "border-border"}`}
    />
  );
}

/** Latest message JSON view (only when Live is OFF; collapsible)
 *
 * Collapsed by default so multiple tiles do not crowd the screen.
 * useTopicMessage only fetches when expanded (zero network load while collapsed).
 */
function LatestMessage({ topicName }: { topicName: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <hr className="border-border" />
      <div className="space-y-1">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setExpanded((v) => !v);
          }}
          className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground"
        >
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          Latest Message
        </button>
        {expanded && <LatestMessageBody topicName={topicName} />}
      </div>
    </>
  );
}

function LatestMessageBody({ topicName }: { topicName: string }) {
  const { data: message, isPending } = useTopicMessage(topicName);
  // isPending: before the HTTP request is issued / during the initial fetch
  // message === null: backend reported "not yet received" (waiting for the next message)
  if (isPending) return <p className="text-xs text-muted-foreground">Loading...</p>;
  if (message == null) return <p className="text-xs text-muted-foreground">Waiting for the next message...</p>;
  return (
    <pre className="rounded bg-muted/30 p-2 text-xs text-muted-foreground overflow-x-auto whitespace-pre-wrap break-all font-mono leading-relaxed">
      {JSON.stringify(message, null, 2)}
    </pre>
  );
}

/** Topic-detail body (quality line / image / detail stats / latest message).
 *
 * For image topics the preview renders directly under the quality line so the video
 * stays visible; the remaining stats follow below it.
 * The panel header is handled by PreviewPane.
 */
export function TopicDetailsBody({ topic }: { topic: TopicInfo }) {
  const isLive = useLiveTopicsStore((s) => s.isLive);
  const setIsLive = useLiveTopicsStore((s) => s.setIsLive);

  // Stop Live mode when switching topics (cleanup on unmount)
  useEffect(() => {
    return () => {
      if (useLiveTopicsStore.getState().isLive) {
        fetch(`/api/topics/live/stop?topic=${encodeURIComponent(topic.name)}`, { method: "POST" });
        setIsLive(false);
      }
    };
  }, [topic.name, setIsLive]);

  return (
    <div className="space-y-3 p-3">
      <QualityLine topic={topic} />
      {isImageTopic(topic.msg_type) && <ImagePreview topicName={topic.name} isLive={isLive} />}
      <hr className="border-border" />
      <StatsDetail topic={topic} />
      {!isLive && <LatestMessage topicName={topic.name} />}
    </div>
  );
}
