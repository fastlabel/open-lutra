/** Header button that appears when a software update is waiting, and applies it after confirmation. */

import { ArrowUpCircle } from "lucide-react";
import { useState } from "react";
import { useApplySystemUpdate } from "@/api/generated/system/system";
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
import { useIsRecording, useSystemUpdate } from "@/hooks/use-api";
import { toast } from "@/stores/toast-store";
import { RestartOverlay } from "./restart-overlay";

export function SystemUpdateButton() {
  // --- Server state ---
  const { data: update } = useSystemUpdate();
  const isRecording = useIsRecording();
  const applyMutation = useApplySystemUpdate();

  // --- Render-only state ---
  const [applied, setApplied] = useState(false);

  if (applied || update?.applying) return <RestartOverlay />;
  if (!update?.available) return null;

  return (
    <AlertDialog>
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <AlertDialogTrigger asChild>
              <Button size="sm" disabled={isRecording || applyMutation.isPending} className="h-7 gap-1.5 text-sm">
                <ArrowUpCircle size={14} />
                Update
              </Button>
            </AlertDialogTrigger>
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          {isRecording ? "Stop recording to update" : "A new version of OpenLUTRA is available"}
        </TooltipContent>
      </Tooltip>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Update OpenLUTRA</AlertDialogTitle>
          <AlertDialogDescription>
            OpenLUTRA restarts to apply the update and is unavailable for about a minute.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel asChild>
            <Button variant="outline" size="sm">
              Cancel
            </Button>
          </AlertDialogCancel>
          <AlertDialogAction asChild>
            <Button
              size="sm"
              onClick={() =>
                applyMutation.mutate(undefined, {
                  onSuccess: () => setApplied(true),
                  onError: (err: unknown) =>
                    toast.error("Update failed", err instanceof Error ? err.message : undefined),
                })
              }
            >
              Update and restart
            </Button>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
