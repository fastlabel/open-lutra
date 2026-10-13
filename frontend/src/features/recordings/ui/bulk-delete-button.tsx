/** Bulk delete button for checked recordings, with tooltip and confirmation dialog. */

import { Loader2, Trash2 } from "lucide-react";
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
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useDeleteRecordings } from "@/hooks/use-api";
import { useAddLog } from "@/hooks/use-topics-stream";
import { toast } from "@/stores/toast-store";
import { useRecordingsStore } from "../store";

export function BulkDeleteButton() {
  const deleteMutation = useDeleteRecordings();
  const addLog = useAddLog();
  const checkedFolders = useRecordingsStore((s) => s.checkedFolders);
  const clearChecked = useRecordingsStore((s) => s.clearChecked);

  if (checkedFolders.size === 0) return null;

  const handleBulkDelete = () => {
    const folders = [...checkedFolders];
    if (folders.length === 0) return;
    deleteMutation.mutate(
      { data: { folders } },
      {
        onSuccess: (resp) => {
          const deleted = resp.status === 200 ? (resp.data as { deleted: string[] }).deleted : [];
          const summary = `Deleted ${deleted.length} recording${deleted.length === 1 ? "" : "s"}`;
          addLog("info", summary);
          // Folders that were already gone are skipped by the backend rather than failing the request.
          const missing = folders.filter((f) => !deleted.includes(f));
          if (missing.length === 0) toast.success(summary);
          else
            toast.error(
              `Deleted ${deleted.length} of ${folders.length} recordings`,
              `Not found: ${missing.join(", ")}`,
            );
          clearChecked();
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Delete failed";
          addLog("danger", `Delete failed: ${msg}`);
          toast.error("Failed to delete recordings", msg);
        },
      },
    );
  };

  return (
    <AlertDialog>
      <Tooltip>
        <TooltipTrigger asChild>
          <AlertDialogTrigger asChild>
            <button
              type="button"
              disabled={deleteMutation.isPending}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-red-400 transition-colors enabled:hover:bg-red-500/20 disabled:text-muted-foreground/40 disabled:cursor-not-allowed"
            >
              {deleteMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
              Delete
            </button>
          </AlertDialogTrigger>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Delete {checkedFolders.size} item{checkedFolders.size === 1 ? "" : "s"}
        </TooltipContent>
      </Tooltip>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete recordings</AlertDialogTitle>
          <AlertDialogDescription>
            Delete {checkedFolders.size} selected recording{checkedFolders.size === 1 ? "" : "s"}? This action cannot be
            undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel asChild>
            <Button variant="outline" size="sm">
              Cancel
            </Button>
          </AlertDialogCancel>
          <AlertDialogAction asChild>
            <Button variant="destructive" size="sm" onClick={handleBulkDelete}>
              Delete
            </Button>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
