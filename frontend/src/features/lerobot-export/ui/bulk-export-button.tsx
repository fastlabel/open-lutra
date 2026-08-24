import { Boxes } from "lucide-react";
import { useState } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useRecordingsStore } from "@/features/recordings";
import { useLeRobotConfig } from "@/hooks/use-api";
import { ExportDialog } from "./export-dialog";

export function BulkExportButton() {
  const { data: config } = useLeRobotConfig();
  const checkedFolders = useRecordingsStore((s) => s.checkedFolders);
  const clearChecked = useRecordingsStore((s) => s.clearChecked);
  const [open, setOpen] = useState(false);

  if (checkedFolders.size === 0) return null;

  const configured = config?.configured ?? false;

  const button = (
    <button
      type="button"
      disabled={!configured}
      onClick={() => setOpen(true)}
      className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-foreground/80 transition-colors enabled:hover:bg-accent disabled:pointer-events-none disabled:text-muted-foreground/40"
    >
      <Boxes size={13} />
      Export to LeRobot
    </button>
  );

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* The disabled button has pointer-events:none, so wrap it in a span
              that receives the hover the tooltip needs to open. */}
          {configured ? button : <span className="cursor-not-allowed">{button}</span>}
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {configured
            ? `Export ${checkedFolders.size} item${checkedFolders.size === 1 ? "" : "s"} to a LeRobot dataset`
            : "No lerobot_export mapping in the active recording config"}
        </TooltipContent>
      </Tooltip>
      <ExportDialog folders={[...checkedFolders]} open={open} onOpenChange={setOpen} onExported={clearChecked} />
    </>
  );
}
