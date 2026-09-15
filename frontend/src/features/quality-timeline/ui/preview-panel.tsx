/** Preview panel: shows video + Joint Position Graph in a collapsible section.
 *
 * Design:
 * - Collapsed by default (resets on each page visit; not persisted)
 * - Calls GET /api/media/video / GET /api/media/joints only when opened
 *   → if not generated yet, enqueue a GenerateMediaJob (the backend manages the queue)
 * - Progress is shown via SSE (`useJobsStream`)
 * - Video uses up to 4 columns, Joint graphs up to 2 columns at small size (controlled by the inner components)
 */

import { ChevronRight, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useGetVideoStatus } from "@/api/generated/media/media";
import type { JobProgressSchema, VideoResponse } from "@/api/generated/schemas";
import { useStartVideoGeneration } from "@/hooks/use-api";
import { useJob } from "@/hooks/use-jobs-stream";
import { JointGraph } from "./joint-graph";
import { VideoGrid } from "./video-grid";

/** Progress badge for the preview header. */
function HeaderProgress({ progress }: { progress?: JobProgressSchema | null }) {
  if (!progress) return null;
  const label = progress.step_label || "Generating";
  const total = progress.total;
  const current = progress.current;
  if (total <= 1) {
    return <span className="text-[13px] text-muted-foreground">{label}</span>;
  }
  return (
    <span className="text-[13px] text-muted-foreground">
      {label} ({current}/{total})
    </span>
  );
}

export function PreviewPanel({ selectedFolder }: { selectedFolder: string }) {
  const [open, setOpen] = useState(false);
  // Destructure mutate / isPending. Putting the whole useMutation return value into deps would
  // re-fire useEffect on reference changes, triggering a flood of POSTs. mutate is returned by
  // react-query as a stable reference and is safe to put in deps.
  const { mutate: startVideoGen, isPending: isStartingVideoGen } = useStartVideoGeneration();

  const { data: videoData } = useGetVideoStatus<VideoResponse>(
    { path: selectedFolder },
    {
      query: {
        enabled: !!selectedFolder && open,
        select: (resp) => resp.data as VideoResponse,
        refetchInterval: (query) => {
          const status = (query.state.data?.data as VideoResponse | undefined)?.status;
          return status === "generating" ? 3000 : false;
        },
      },
    },
  );

  useEffect(() => {
    if (open && selectedFolder && videoData?.status === "not_generated" && !isStartingVideoGen) {
      startVideoGen({ params: { path: selectedFolder } });
    }
  }, [open, selectedFolder, videoData?.status, isStartingVideoGen, startVideoGen]);

  // Progress received via SSE (preferred). The video response's progress is the fallback.
  const job = useJob(videoData?.job_id ?? null);
  const progress: JobProgressSchema | null | undefined =
    job?.progress ?? (videoData?.progress as JobProgressSchema | null | undefined);
  const isGenerating = videoData?.status === "generating";

  return (
    <div className="rounded border border-border bg-muted/10">
      {/* Header (click to toggle) */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/20 transition-colors"
        aria-expanded={open}
      >
        <ChevronRight size={14} className={`text-muted-foreground transition-transform ${open ? "rotate-90" : ""}`} />
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Preview</span>
        <div className="ml-auto flex items-center gap-2">
          {isGenerating && (
            <>
              <Loader2 size={12} className="animate-spin text-muted-foreground/50" />
              <HeaderProgress progress={progress} />
            </>
          )}
        </div>
      </button>

      {/* Body (mount only when expanded so the API is not called) */}
      {open && (
        <div className="border-t border-border p-3 space-y-4">
          <VideoGrid selectedFolder={selectedFolder} enabled={open} />
          <JointGraph selectedFolder={selectedFolder} enabled={open} />
        </div>
      )}
    </div>
  );
}
