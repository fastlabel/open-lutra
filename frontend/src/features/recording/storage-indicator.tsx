/** Free space on the recording volume, shown in the recording action bar.
 *
 * A snapshot rather than a live gauge: it is read when the recording screen
 * mounts and again once post-recording jobs finish writing (see
 * use-jobs-stream.ts). Nothing refreshes it while a recording is in progress, so
 * the refresh button is how an operator asks for a current reading mid-session.
 */

import { HardDrive, RotateCw } from "lucide-react";
import type { StorageInfo } from "@/api/generated/schemas";
import { useStorage } from "@/hooks/use-api";
import { formatCapacity } from "@/lib/format";

/** The reading, plus a tooltip naming what it is or why there is no number.
 *
 * A first load in flight, a request that failed, and a volume the backend could
 * not inspect are three different situations, and only the last one knows a path
 * to name — so they must not collapse into one string.
 */
function readout(storage: StorageInfo | undefined, isPending: boolean): { text: string; title: string } {
  if (isPending) return { text: "Reading…", title: "Reading the free space of the recording volume" };
  if (!storage) return { text: "Read failed", title: "Could not reach the backend to read the recording volume" };
  if (storage.free_bytes == null) return { text: "Unavailable", title: `Cannot inspect ${storage.path}` };
  return { text: `${formatCapacity(storage.free_bytes)} free`, title: storage.path };
}

export function StorageIndicator() {
  const { data: storage, isPending, isFetching, refetch } = useStorage();

  const { text, title } = readout(storage, isPending);

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
      <span className="text-[13px] text-muted-foreground" title={title}>
        {text}
      </span>
    </div>
  );
}
