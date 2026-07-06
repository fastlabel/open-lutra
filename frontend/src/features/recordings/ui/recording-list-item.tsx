/** Shared row component for the recording list: checkbox, label (editable), meta info, delete (with confirmation).
 *
 * Clicking the row navigates to `/recordings/{folder}` (the MCAP detail page).
 */

import { useNavigate } from "@tanstack/react-router";
import { Check, Loader2, Pencil, Trash2, X } from "lucide-react";
import { memo, useState } from "react";
import type { FileEntry } from "@/api/generated/schemas";
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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { UploadBadge } from "@/features/upload";
import { ValidationBadge } from "@/features/validation";
import { useDeleteRecordings, useRenameRecording } from "@/hooks/use-api";
import { useAddLog } from "@/hooks/use-topics-stream";
import { useRecordingsStore } from "../store";
import { FileMetaLine } from "./file-meta-line";
import { MetaEditDialog } from "./meta-edit-dialog";

// Memoized: the list renders many rows, and only the row whose `entry` (or its
// own checked state, read via a store selector inside) changes should re-render.
export const RecordingListItem = memo(function RecordingListItem({
  entry,
  checkDisabled,
  canRename,
}: {
  entry: FileEntry;
  /** Disable the check operation (e.g. during recording). */
  checkDisabled?: boolean;
  /** Allow renaming on double-click. */
  canRename?: boolean;
}) {
  // --- Routing ---
  const navigate = useNavigate();

  // --- Server state (TanStack Query) ---
  const isChecked = useRecordingsStore((s) => s.checkedFolders.has(entry.name));
  const toggleCheck = useRecordingsStore((s) => s.toggleCheck);

  const deleteMutation = useDeleteRecordings();
  const renameMutation = useRenameRecording();
  const addLog = useAddLog();

  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [metaDialogOpen, setMetaDialogOpen] = useState(false);

  const commitEdit = () => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== entry.name) {
      renameMutation.mutate(
        { data: { old_name: entry.name, new_name: trimmed } },
        {
          onSuccess: () => {
            addLog("info", `Renamed: ${entry.name} → ${trimmed}`);
          },
          onError: (err: unknown) => {
            const msg = err instanceof Error ? err.message : "Rename failed";
            addLog("danger", `Rename failed (${entry.name}): ${msg}`);
          },
        },
      );
    }
    setEditing(false);
  };

  const handleDelete = () => {
    deleteMutation.mutate(
      { data: { folders: [entry.name] } },
      {
        onSuccess: (resp) => {
          const count = resp.status === 200 ? (resp.data as { deleted: string[] }).deleted.length : 0;
          addLog("info", `Deleted ${count} recording${count === 1 ? "" : "s"}`);
          if (isChecked) toggleCheck(entry.name);
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Delete failed";
          addLog("danger", `Delete failed: ${msg}`);
        },
      },
    );
  };

  return (
    <div
      className="flex items-center gap-3 border-b border-border px-4 py-2 transition-colors cursor-pointer hover:bg-muted/50"
      onClick={() =>
        navigate({
          from: "/recordings",
          to: "/recordings/$folder",
          params: { folder: encodeURIComponent(entry.path) },
          // Carry the active filter into the detail page so its prev/next pager walks the same view.
          search: (prev) => prev,
        })
      }
      onDoubleClick={
        canRename
          ? (e) => {
              e.stopPropagation();
              setEditValue(entry.name);
              setEditing(true);
            }
          : undefined
      }
    >
      {/* Checkbox */}
      <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
        <Checkbox
          checked={isChecked}
          disabled={checkDisabled}
          onCheckedChange={() => toggleCheck(entry.name)}
          aria-label={`Select ${entry.name}`}
        />
      </div>

      <ValidationBadge status={entry.validation_overall_status} />
      <UploadBadge entry={entry} />

      {/* Two-line text */}
      <div className="min-w-0 flex-1">
        {/* Title line: prefer task_name, fall back to folder name. When task_name is set, show the folder name muted alongside. */}
        {editing ? (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
            <input
              ref={(el) => el?.focus()}
              className="min-w-0 flex-1 bg-muted/50 border border-border rounded px-1.5 py-0.5 text-sm text-foreground outline-none focus:border-ring"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitEdit();
                if (e.key === "Escape") setEditing(false);
              }}
              onBlur={commitEdit}
            />
          </div>
        ) : (
          <div className="flex min-w-0 items-center gap-2">
            <div className="truncate text-sm font-medium" title={entry.task_name ?? entry.name}>
              {entry.task_name ?? entry.name}
            </div>
            {entry.task_name && (
              <div className="truncate text-xs text-muted-foreground" title={entry.name}>
                {entry.name}
              </div>
            )}
            {entry.tags.length > 0 && (
              <div className="flex shrink-0 items-center gap-1">
                {entry.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-[11px] py-0 px-1.5 font-normal">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
        {/* Meta line: size, topic count, timestamp */}
        <FileMetaLine
          size={entry.size}
          topicCount={entry.topic_count}
          recordingStartNs={entry.recording_start_ns}
          durationNs={entry.duration_ns}
          messageCount={entry.message_count}
        />
      </div>

      {/* Action buttons */}
      <div className="flex shrink-0 items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
        {/* Metadata edit button (for task_name / tags). Hidden while renaming. */}
        {!editing && (
          <button
            type="button"
            className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
            onClick={() => setMetaDialogOpen(true)}
            title="Edit metadata"
          >
            <Pencil size={14} />
          </button>
        )}
        <MetaEditDialog entry={entry} open={metaDialogOpen} onOpenChange={setMetaDialogOpen} />

        {/* While editing: commit/cancel buttons (left of delete) */}
        {editing && (
          <>
            <button
              type="button"
              className="rounded p-1 text-emerald-400 hover:bg-muted/50"
              onClick={commitEdit}
              title="Confirm"
            >
              <Check size={14} />
            </button>
            <button
              type="button"
              className="rounded p-1 text-muted-foreground hover:bg-muted/50"
              onMouseDown={(e) => {
                e.preventDefault();
                setEditing(false);
              }}
              title="Cancel"
            >
              <X size={14} />
            </button>
          </>
        )}

        {/* Delete button (with confirmation dialog; disabled while editing) */}
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <button
              type="button"
              className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-red-500/20 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed"
              disabled={editing || deleteMutation.isPending}
              title="Delete"
            >
              {deleteMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            </button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete recording</AlertDialogTitle>
              <AlertDialogDescription>Delete "{entry.name}"? This action cannot be undone.</AlertDialogDescription>
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
      </div>
    </div>
  );
});
