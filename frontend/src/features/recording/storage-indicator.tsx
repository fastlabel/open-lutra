/** Free space on the recording volume, shown in the recording action bar.
 *
 * A snapshot rather than a live gauge: it is read when the recording screen
 * mounts and again once post-recording jobs finish writing (see
 * use-jobs-stream.ts). Nothing refreshes it while a recording is in progress, so
 * the refresh button is how an operator asks for a current reading mid-session.
 */

import { HardDrive, RotateCw } from "lucide-react";
import { useStorage } from "@/hooks/use-api";
import { formatCapacity } from "@/lib/format";

export function StorageIndicator() {
  const { data: storage, isFetching, refetch } = useStorage();

  return (
    <div className="flex min-w-[150px] flex-col justify-center gap-1">
      <div className="flex items-center gap-1.5">
        <HardDrive size={14} className="text-foreground" />
        <span className="text-[13px] font-medium text-foreground">Storage</span>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          title="Refresh free space"
          aria-label="Refresh free space"
          className="text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RotateCw size={13} className={isFetching ? "animate-spin" : undefined} />
        </button>
      </div>
      {/* The path names the volume that was measured, and is the only clue to
          work with when it cannot be read. */}
      <span className="text-[13px] text-muted-foreground" title={storage?.path}>
        {storage?.free_bytes != null ? `${formatCapacity(storage.free_bytes)} free` : "Unavailable"}
      </span>
    </div>
  );
}
