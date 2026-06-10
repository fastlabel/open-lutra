/** Toolbar button that exports the checked recordings to a LeRobot dataset. */

import { Boxes } from "lucide-react";
import { useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRecordingsStore } from "@/features/recordings";
import { ExportDialog } from "./export-dialog";

export function BulkExportButton() {
  const checkedFolders = useRecordingsStore((s) => s.checkedFolders);
  const clearChecked = useRecordingsStore((s) => s.clearChecked);
  const [open, setOpen] = useState(false);

  if (checkedFolders.size === 0) return null;

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-foreground/80 transition-colors hover:bg-accent"
          >
            <Boxes size={13} />
            Export to LeRobot
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Export {checkedFolders.size} item{checkedFolders.size === 1 ? "" : "s"} to a LeRobot dataset
        </TooltipContent>
      </Tooltip>
      <ExportDialog folders={[...checkedFolders]} open={open} onOpenChange={setOpen} onExported={clearChecked} />
    </>
  );
}
