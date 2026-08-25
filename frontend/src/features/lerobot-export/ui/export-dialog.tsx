/** Dialog for exporting selected recordings to a LeRobot v3.0 dataset.
 *
 * The topic→feature mapping comes from the active recording config's
 * `lerobot_export` section, so this dialog only needs an output name. After
 * submission it keeps showing the job's live progress / result (driven by the
 * jobs SSE cache) so there is visible feedback in normal mode too — the
 * StatusBar pill and log viewer are dev-/monitor-only and absent on /recordings.
 * The dataset is written under <output_dir>/_lerobot_exports/<name>/.
 */

import { CheckCircle2, Download, Loader2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useStartLeRobotExport } from "@/api/generated/lerobot/lerobot";
import type { ExportResponse, JobSchema, LeRobotConfigResponse } from "@/api/generated/schemas";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLeRobotConfig } from "@/hooks/use-api";
import { useJob } from "@/hooks/use-jobs-stream";

/** Active robot mapping summary shown above the output-name field. */
function MappingInfo({ config }: { config: LeRobotConfigResponse | undefined }) {
  if (!config?.configured) return null;
  return (
    <div className="text-sm text-muted-foreground">
      {config.robot_type} · cameras: {config.cameras.join(", ") || "(none)"}
    </div>
  );
}

/** Live progress / result of the running export job. */
function ExportProgress({ job, outputName }: { job: JobSchema | undefined; outputName: string }) {
  if (job?.status === "completed") {
    // A plain <a download> (user-gesture triggered) zips and streams the dataset
    // straight to the browser's download folder — no popup blocker, no blob in memory.
    return (
      <div className="space-y-3">
        <div className="flex items-start gap-2 text-sm">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-green-500" />
          <span>
            Export completed: <code>_lerobot_exports/{outputName}/</code>
          </span>
        </div>
        <Button asChild size="sm" variant="outline">
          <a href={`/api/lerobot/exports/${encodeURIComponent(outputName)}/download`} download>
            <Download size={16} />
            Download .zip
          </a>
        </Button>
      </div>
    );
  }
  if (job?.status === "failed") {
    return (
      <div className="flex items-start gap-2 text-sm text-red-400">
        <XCircle size={16} className="mt-0.5 shrink-0" />
        <span>Export failed: {job.error ?? "unknown error"}</span>
      </div>
    );
  }
  const progress = job?.progress;
  const fraction = progress && progress.total > 1 ? ` (${progress.current}/${progress.total})` : "";
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 size={16} className="shrink-0 animate-spin" />
      <span>
        {progress?.step_label || "Exporting…"}
        {fraction}
      </span>
    </div>
  );
}

export function ExportDialog({
  folders,
  open,
  onOpenChange,
  onExported,
}: {
  folders: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onExported: () => void;
}) {
  // --- Server state ---
  const { data: config } = useLeRobotConfig();
  const mutation = useStartLeRobotExport();

  // --- Local state (reset each time the dialog opens) ---
  const [outputName, setOutputName] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // --- Streaming: track the export job once it is enqueued ---
  const job = useJob(jobId);

  useEffect(() => {
    if (open) {
      setOutputName("");
      setJobId(null);
      setSubmitError(null);
    }
  }, [open]);

  const canSubmit =
    (config?.configured ?? false) && outputName.trim() !== "" && folders.length > 0 && !mutation.isPending;

  const handleExport = () => {
    setSubmitError(null);
    mutation.mutate(
      { data: { folders, output_name: outputName.trim() } },
      {
        onSuccess: (resp) => setJobId((resp.data as ExportResponse).job_id),
        onError: (err: unknown) => setSubmitError(err instanceof Error ? err.message : "Export failed"),
      },
    );
  };

  // Always dismiss the dialog (the job keeps running in the background); on
  // success also clear the recording selection. Both must run: BulkExportButton
  // stays mounted while returning null, so leaving `open` true would re-pop the
  // dialog uninvited the next time a recording is checked.
  const handleClose = () => {
    if (job?.status === "completed") onExported();
    onOpenChange(false);
  };

  return (
    // Route Escape / overlay clicks through handleClose so they behave exactly
    // like the Close button (e.g. clearing the selection after a completed export).
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) handleClose();
      }}
    >
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Export to LeRobot</DialogTitle>
          <DialogDescription>
            {folders.length} recording{folders.length === 1 ? "" : "s"} → one LeRobot v3.0 dataset (one episode each).
          </DialogDescription>
        </DialogHeader>

        {jobId === null ? (
          <>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label>Mapping</Label>
                <MappingInfo config={config} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lerobot-output">Output name</Label>
                <Input
                  id="lerobot-output"
                  value={outputName}
                  onChange={(e) => setOutputName(e.target.value)}
                  placeholder="e.g. pick_and_place_v1"
                  autoFocus
                />
                <p className="text-[13px] text-muted-foreground">Written to _lerobot_exports/&lt;name&gt;/</p>
              </div>
              {submitError && <p className="text-[13px] text-red-400">{submitError}</p>}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleExport} disabled={!canSubmit}>
                {mutation.isPending ? "Starting…" : "Export"}
              </Button>
            </div>
          </>
        ) : (
          <>
            <div className="py-2">
              <ExportProgress job={job} outputName={outputName.trim()} />
            </div>
            <div className="flex justify-end pt-2">
              <Button size="sm" variant={job?.status === "completed" ? "default" : "outline"} onClick={handleClose}>
                Close
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
