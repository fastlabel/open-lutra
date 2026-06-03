/** Recording page: top action bar, left sidebar TOPICS (collapsible), and on the right PREVIEW (top) and LOSS RATE/LOG (bottom). */

import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef } from "react";
import { Group, Panel } from "react-resizable-panels";
import { updateSubscriptions } from "@/api/generated/topics/topics";
import { ResizeHandleH, ResizeHandleV } from "@/components/ui/resize-handle";
import { LiveTopicPreview, LiveTopics, useLiveTopicsStore } from "@/features/live-topics";
import { MonitorTabs, MonitorTabsHeader } from "@/features/monitor";
import { RecordingCompletionBanner, RecordingControl, useRecordingStore } from "@/features/recording";
import { useConfig, useIsRecording } from "@/hooks/use-api";
import { useTopicsStream } from "@/hooks/use-topics-stream";
import { usePanelStore } from "@/stores/panel-store";

function RecorderPage() {
  // --- Server state (TanStack Query) ---
  const { data: config } = useConfig();
  const isRecordingForStream = useIsRecording();

  // --- Streaming (SSE) ---
  const stopLiveMonitor = useRecordingStore((s) => s.stopLiveMonitorDuringRecording);
  useTopicsStream(!isRecordingForStream || !stopLiveMonitor);

  // --- Side effects ---
  // Initialize the selection from the config's default topics and sync with the backend (one-time only).
  const initializeTopics = useLiveTopicsStore((s) => s.initializeTopics);
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current || !config?.default_topics) return;
    initialized.current = true;
    initializeTopics(config.default_topics);
    updateSubscriptions({ topics: config.default_topics }).catch(() => {});
  }, [config, initializeTopics]);

  // --- Render-only state ---
  const topicsSidebarOpen = usePanelStore((s) => s.topicsSidebarOpen);
  const bottomPaneMinimized = usePanelStore((s) => s.bottomPaneMinimized);

  // Right side (PREVIEW + QUALITY/LOG): vertical split when expanded, or PREVIEW + thin tab bar when minimized.
  const rightSide = bottomPaneMinimized ? (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1">
        <LiveTopicPreview />
      </div>
      <MonitorTabsHeader placement="bottom-bar" />
    </div>
  ) : (
    <Group orientation="vertical" style={{ height: "100%" }}>
      <Panel defaultSize="65%" minSize="30%" id="preview">
        <LiveTopicPreview />
      </Panel>
      <ResizeHandleV />
      <Panel defaultSize="35%" minSize="10%" maxSize="60%" id="bottom">
        <MonitorTabs />
      </Panel>
    </Group>
  );

  return (
    <div className="flex h-full flex-col bg-background">
      <RecordingControl />
      <RecordingCompletionBanner />
      <div className="flex-1 overflow-hidden">
        {topicsSidebarOpen ? (
          <Group orientation="horizontal" style={{ height: "100%" }}>
            <Panel defaultSize="25%" minSize="15%" maxSize="50%" id="topics">
              <LiveTopics />
            </Panel>
            <ResizeHandleH />
            <Panel minSize="40%" id="main">
              {rightSide}
            </Panel>
          </Group>
        ) : (
          <div className="flex h-full">
            <LiveTopics />
            <div className="min-w-0 flex-1">{rightSide}</div>
          </div>
        )}
      </div>
    </div>
  );
}

export const Route = createFileRoute("/")({
  component: RecorderPage,
});
