/** Video grid: displays MP4s in a dynamic layout based on the number of cameras (up to 4 columns). */

import { Loader2, Video } from "lucide-react";
import { useGetVideoStatus } from "@/api/generated/media/media";
import type { JobProgressSchema, VideoResponse } from "@/api/generated/schemas";
import { useJob } from "@/hooks/use-jobs-stream";
import { VideoPlayer } from "./video-player";

/** Progress indicator (prefers SSE-delivered job progress, falls back to the video response's progress). */
function ProgressIndicator({ progress }: { progress?: JobProgressSchema | null }) {
  if (!progress) return <span>Generating video...</span>;

  const label = progress.step_label || "Generating video...";
  const total = progress.total;
  const current = progress.current;
  if (total <= 1) return <span>{label}</span>;

  const pct = Math.round((current / total) * 100);
  return (
    <div className="flex items-center gap-2">
      <span>
        {label} ({current}/{total})
      </span>
      <div className="h-1.5 w-24 rounded-full bg-muted/40 overflow-hidden">
        <div className="h-full rounded-full bg-emerald-400/70 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/** Extracts a camera name from an MP4 filename. */
function cameraLabel(filename: string): string {
  // "observation.images.head_cam.mp4" → "head_cam"
  return filename.replace(/^observation\.images\./, "").replace(/\.mp4$/, "");
}

function gridCols(count: number): string {
  if (count <= 1) return "grid-cols-1";
  if (count === 2) return "grid-cols-2";
  if (count === 3) return "grid-cols-3";
  return "grid-cols-2 md:grid-cols-3 lg:grid-cols-4";
}

export function VideoGrid({ selectedFolder, enabled = true }: { selectedFolder: string; enabled?: boolean }) {
  const { data, isLoading } = useGetVideoStatus<VideoResponse>(
    { path: selectedFolder },
    {
      query: {
        enabled: !!selectedFolder && enabled,
        select: (resp) => resp.data as VideoResponse,
        // Progress is available via SSE, but poll as a fallback while status=generating
        refetchInterval: (query) => {
          const status = (query.state.data?.data as VideoResponse | undefined)?.status;
          return status === "generating" ? 3000 : false;
        },
      },
    },
  );

  const job = useJob(data?.job_id ?? null);
  const progress: JobProgressSchema | null | undefined =
    job?.progress ?? (data?.progress as JobProgressSchema | null | undefined);

  if (data?.status === "error") {
    return <p className="py-4 text-center text-[13px] text-red-400/80">{data.error}</p>;
  }

  const isGenerating = data?.status === "generating";
  const videos = data?.videos ?? [];

  const apiBase = "/api/media/video/file";
  const targetParam = encodeURIComponent(selectedFolder);

  // When the MP4 has not been generated yet: show header + Loading / progress.
  // (To avoid a blank gap while the status transitions not_generated → generating → ready,
  //  bundle isLoading, waiting-for-mutation, and generating into a single placeholder here.)
  const showPlaceholder = videos.length === 0;

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Video size={14} className="text-muted-foreground" />
        <span className="text-[13px] font-semibold uppercase tracking-wider text-muted-foreground">Video</span>
        {(isLoading || showPlaceholder || isGenerating) && (
          <>
            <Loader2 size={12} className="animate-spin text-muted-foreground/50" />
            <span className="text-[13px] text-muted-foreground font-normal normal-case tracking-normal">
              {isGenerating ? <ProgressIndicator progress={progress} /> : <span>Generating video...</span>}
            </span>
          </>
        )}
      </div>

      {showPlaceholder ? (
        <div className="flex items-center justify-center rounded border border-border bg-muted/10 py-10 text-[13px] text-muted-foreground">
          Generating video...
        </div>
      ) : (
        <div className={`grid gap-2 ${gridCols(videos.length)}`}>
          {videos.map((filename) => (
            <VideoPlayer
              key={filename}
              src={`${apiBase}?path=${targetParam}&name=${encodeURIComponent(filename)}`}
              label={cameraLabel(filename)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
