/** Preview tile: a mini-dashboard for one topic, with the X button.
 *
 * - Header holds the topic name and a close X
 * - Body is TopicDetailsBody (quality line / image / detail stats / latest message)
 */

import { X } from "lucide-react";
import type { TopicInfo } from "@/api/generated/schemas";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useLiveTopicsStore } from "../store";
import { TopicDetailsBody } from "./topic-details";

export function TopicPreviewTile({ topic }: { topic: TopicInfo }) {
  const removePreviewedTopic = useLiveTopicsStore((s) => s.removePreviewedTopic);

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded border border-border bg-background">
      <div className="flex items-center justify-between gap-2 border-b border-border px-2 py-1.5">
        <span className="min-w-0 flex-1 truncate font-mono text-sm text-foreground" title={topic.name}>
          {topic.name}
        </span>
        <button
          type="button"
          onClick={() => removePreviewedTopic(topic.name)}
          className="text-muted-foreground hover:text-foreground"
          title="Remove from preview"
        >
          <X size={14} />
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <ScrollArea className="h-full">
          <TopicDetailsBody topic={topic} />
        </ScrollArea>
      </div>
    </div>
  );
}
