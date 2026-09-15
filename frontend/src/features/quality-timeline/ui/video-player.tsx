/** Individual video player: wraps the <video> tag. Keeps playheadSec and currentTime in sync.
 *
 * To work around the browser's connection limits when many cameras load simultaneously,
 * load completion is detected via the loadeddata event, and load failures are retried.
 */

import { Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQualityTimelineStore } from "../store";

/** Maximum number of load retries */
const MAX_RETRIES = 3;

export function VideoPlayer({ src, label }: { src: string; label: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const playheadSec = useQualityTimelineStore((s) => s.playheadSec);
  const isPlaying = useQualityTimelineStore((s) => s.isPlaying);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const retryCount = useRef(0);

  const reload = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    setError(false);
    setLoaded(false);
    // Append a timestamp to src to bypass cache
    video.src = `${src}${src.includes("?") ? "&" : "?"}_t=${Date.now()}`;
    video.load();
  }, [src]);

  // Metadata load complete (resolution is known and rendering can proceed correctly)
  const handleLoaded = useCallback(() => {
    setLoaded(true);
    setError(false);
    retryCount.current = 0;
  }, []);

  // Auto-retry on error
  const handleError = useCallback(() => {
    if (retryCount.current < MAX_RETRIES) {
      retryCount.current += 1;
      // Delay slightly before retrying (to spread out from other videos)
      setTimeout(reload, 500 * retryCount.current);
    } else {
      setError(true);
    }
  }, [reload]);

  // playhead → video.currentTime sync (follow seek operations even during playback)
  useEffect(() => {
    const video = videoRef.current;
    if (!video || !loaded) return;
    // During playback the video advances on its own, but follow seeks (big jumps)
    if (Math.abs(video.currentTime - playheadSec) > 0.3) {
      video.currentTime = playheadSec;
    }
  }, [playheadSec, loaded]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !loaded) return;
    if (isPlaying) {
      video.currentTime = useQualityTimelineStore.getState().playheadSec;
      video.play().catch(() => {});
    } else {
      video.pause();
      // Snap to the exact position on pause
      video.currentTime = useQualityTimelineStore.getState().playheadSec;
    }
  }, [isPlaying, loaded]);

  return (
    <div className="space-y-1">
      <span className="text-[13px] text-muted-foreground truncate block">{label}</span>
      <div className="relative">
        {!loaded && !error && (
          <div className="flex items-center justify-center rounded border border-border bg-black/50 aspect-video">
            <Loader2 size={16} className="animate-spin text-muted-foreground" />
          </div>
        )}
        <video
          ref={videoRef}
          src={src}
          className={`w-full rounded border border-border bg-black ${loaded ? "" : "hidden"}`}
          muted
          playsInline
          preload="metadata"
          onLoadedMetadata={handleLoaded}
          onError={handleError}
        />
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60 rounded">
            <button
              type="button"
              onClick={reload}
              className="flex items-center gap-1.5 rounded bg-muted px-2 py-1 text-[13px] text-muted-foreground hover:text-foreground"
            >
              <RefreshCw size={12} />
              Reload
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
