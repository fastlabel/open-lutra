/** Bulk tag / metadata edit button for checked recordings. */

import { Pencil } from "lucide-react";
import { useMemo, useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRecordingsStore } from "../store";
import { BulkMetaEditDialog } from "./bulk-meta-edit-dialog";

export function BulkEditButton() {
  const checkedFolders = useRecordingsStore((s) => s.checkedFolders);
  const clearChecked = useRecordingsStore((s) => s.clearChecked);
  const [open, setOpen] = useState(false);
  // The dialog memoizes on `folders`, so hand it the same array until the selection changes.
  const folders = useMemo(() => [...checkedFolders], [checkedFolders]);

  if (checkedFolders.size === 0) return null;

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
          >
            <Pencil size={13} />
            Edit
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Edit tags and metadata of {checkedFolders.size} item
          {checkedFolders.size === 1 ? "" : "s"}
        </TooltipContent>
      </Tooltip>
      <BulkMetaEditDialog folders={folders} open={open} onOpenChange={setOpen} onSaved={clearChecked} />
    </>
  );
}
