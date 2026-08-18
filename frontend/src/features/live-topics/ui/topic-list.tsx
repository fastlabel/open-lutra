/** Topic list: fetches SSE stats, computes the display list, and renders TopicItem rows. */

import { PanelLeftClose, Radio, RotateCcw, Search, X } from "lucide-react";
import { useMemo, useState } from "react";
import type { TopicInfo } from "@/api/generated/schemas";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useConfig, useResetBaseline } from "@/hooks/use-api";
import { useTopicStats } from "@/hooks/use-topics-stream";
import { sortTopicsByCategory } from "@/lib/topic-sort";
import { usePanelStore } from "@/stores/panel-store";
import { useLiveTopicsStore } from "../store";
import { TopicItem } from "./topic-item";

export function TopicList() {
  const clearPreviewedTopics = useLiveTopicsStore((s) => s.clearPreviewedTopics);
  const isLive = useLiveTopicsStore((s) => s.isLive);
  const selectedTopics = useLiveTopicsStore((s) => s.selectedTopics);
  const [filter, setFilter] = useState("");
  const { data: config } = useConfig();

  // Topic stats from SSE
  const topicStats = useTopicStats();

  // YAML default_topics that have not yet appeared in the SSE stream are surfaced
  // as placeholder rows so the user can see what is missing (rendered with a hollow dot).
  const defaultTopics = config?.default_topics;
  const { allTopics, missingDefaultSet } = useMemo(() => {
    const knownNames = new Set(topicStats.map((t) => t.name));
    const missingNames = (defaultTopics ?? []).filter((name) => !knownNames.has(name));
    const placeholders: TopicInfo[] = missingNames.map((name) => ({
      name,
      msg_type: "unknown",
      actual_hz: 0,
      status: "inactive",
      message_count: 0,
      is_subscribed: false,
      baseline_hz: null,
      baseline_fixed: false,
      loss_rate: 0,
      drop_count: 0,
      continuity_score: 1,
      qos_reliability: "",
    }));
    return {
      allTopics: [...topicStats, ...placeholders] as TopicInfo[],
      missingDefaultSet: new Set(missingNames),
    };
  }, [topicStats, defaultTopics]);

  // Filter and unify sort order.
  // Sort priority:
  //   1. Selected topics (recording targets) come first
  //   2. Category (images → joint)
  //   3. Alphabetical (handled by sortTopicsByCategory)
  // Prevents selected/unselected rows from being scattered, so recording targets stay grouped and visible.
  const displayTopics = useMemo(() => {
    const filtered = filter ? allTopics.filter((t) => t.name.toLowerCase().includes(filter.toLowerCase())) : allTopics;
    const sorted = sortTopicsByCategory(
      filtered,
      (t) => t.name,
      (t) => t.msg_type,
    );
    // Selected first, unselected after (sortTopicsByCategory order preserved within each group)
    const selected: TopicInfo[] = [];
    const unselected: TopicInfo[] = [];
    for (const t of sorted) {
      if (selectedTopics.has(t.name)) selected.push(t);
      else unselected.push(t);
    }
    return [...selected, ...unselected];
  }, [allTopics, filter, selectedTopics]);

  const resetBaseline = useResetBaseline();
  const toggleTopicsSidebar = usePanelStore((s) => s.toggleTopicsSidebar);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          <Radio size={14} />
          Topics
        </span>
        <div className="flex items-center gap-1">
          <Badge variant="secondary" className="h-5 px-1.5 text-xs">
            {displayTopics.length}/{allTopics.length}
          </Badge>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-5 w-5"
                disabled={resetBaseline.isPending}
                onClick={() => resetBaseline.mutate()}
              >
                <RotateCcw size={12} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Reset baseline Hz</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon" className="h-5 w-5" onClick={toggleTopicsSidebar}>
                <PanelLeftClose size={12} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Collapse sidebar</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Search */}
      <div className="relative border-b border-border px-3 py-1.5">
        <Search size={13} className="absolute left-5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter topics..."
          className="w-full bg-transparent pl-6 pr-6 text-xs text-foreground placeholder:text-muted-foreground outline-none"
        />
        {filter && (
          <button
            type="button"
            onClick={() => setFilter("")}
            className="absolute right-5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X size={12} />
          </button>
        )}
      </div>

      {/* Topic list (clicking the empty area clears the entire preview; disabled while Live).
          The `[&_[data-slot=scroll-area-viewport]>div]:!block` override forces the Radix Viewport's
          inner wrapper to be block-level (its default `display: table` lets the row grow with content
          and breaks the topic-name truncation when the sidebar is narrow). */}
      <ScrollArea
        className="flex-1 [&_[data-slot=scroll-area-viewport]>div]:!block"
        onClick={() => {
          if (!isLive) clearPreviewedTopics();
        }}
      >
        <div className="py-1">
          {displayTopics.map((topic) => (
            <TopicItem key={topic.name} topic={topic} isMissing={missingDefaultSet.has(topic.name)} />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
