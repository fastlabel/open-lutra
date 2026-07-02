/** Latest-record banner: persistent reference to the most recent recording, with navigation to its detail page, a delete action, and a dismiss button. */

import { useNavigate } from "@tanstack/react-router";
import { ArrowRight, FolderOpen, Loader2, Trash2, X } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { useDeleteRecordings } from "@/hooks/use-api";
import { useAddLog } from "@/hooks/use-topics-stream";
import { formatDuration, formatSize } from "@/lib/format";
import { toast } from "@/stores/toast-store";
import { useRecordingStore } from "./store";

export function RecordingCompletionBanner() {
  const navigate = useNavigate();
  const finished = useRecordingStore((s) => s.finishedRecording);
  const dismiss = useRecordingStore((s) => s.dismissFinishedRecording);

  const deleteMutation = useDeleteRecordings();
  const addLog = useAddLog();

  if (!finished) return null;

  const meta: string[] = [formatDuration(finished.durationSec)];
  if (finished.messageCount != null) meta.push(`${finished.messageCount.toLocaleString()} msgs`);
  if (finished.topicCount != null) meta.push(`${finished.topicCount} topics`);
  if (finished.size > 0) meta.push(formatSize(finished.size));

  const handleDelete = () =>
    deleteMutation.mutate(
      { data: { folders: [finished.name] } },
      {
        onSuccess: () => {
          addLog("info", `Deleted recording: ${finished.name}`);
          toast.success("Recording deleted", finished.name);
          dismiss();
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Delete failed";
          addLog("danger", `Delete failed: ${msg}`);
          toast.error("Delete failed", msg);
        },
      },
    );

  return (
    <div className="flex items-center gap-3 border-b border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-[13px] text-emerald-300">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="font-medium text-emerald-200">Latest record</span>
        <button
          type="button"
          onClick={() => navigate({ to: "/recordings/$folder", params: { folder: encodeURIComponent(finished.path) } })}
          className="flex items-center gap-1 truncate font-mono text-emerald-300 hover:text-emerald-200 hover:underline"
          title={finished.path}
        >
          <span className="truncate">{finished.name}</span>
          <FolderOpen size={12} className="flex-none" />
        </button>
        <span className="text-emerald-400/70">{meta.join(" · ")}</span>
      </div>

      {/* Discard the recording that was just made (e.g. a bad take), with confirmation. */}
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <button
            type="button"
            disabled={deleteMutation.isPending}
            className="flex items-center gap-1.5 rounded-md border border-emerald-500/30 px-2.5 py-1 text-emerald-200 hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleteMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
            Delete
          </button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete recording</AlertDialogTitle>
            <AlertDialogDescription>Delete "{finished.name}"? This action cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="outline" size="sm">
                Cancel
              </Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button variant="destructive" size="sm" onClick={handleDelete}>
                Delete
              </Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <button
        type="button"
        onClick={() => navigate({ to: "/recordings/$folder", params: { folder: encodeURIComponent(finished.path) } })}
        className="flex items-center gap-1.5 rounded-md border border-emerald-500/30 px-2.5 py-1 text-emerald-200 hover:bg-emerald-500/10"
      >
        Open details
        <ArrowRight size={13} />
      </button>
      <button
        type="button"
        onClick={dismiss}
        aria-label="Close"
        className="rounded p-1 text-emerald-400/70 hover:bg-emerald-500/10 hover:text-emerald-200"
      >
        <X size={14} />
      </button>
    </div>
  );
}
