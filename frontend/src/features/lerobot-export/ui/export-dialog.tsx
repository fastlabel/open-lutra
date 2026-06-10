/** Dialog for exporting selected recordings to a LeRobot v3.0 dataset.
 *
 * The topic→feature mapping comes from the active robot config's
 * `lerobot_export` section, so this dialog only needs an output name. After
 * submission it keeps showing the job's live progress / result (driven by the
 * jobs SSE cache) so there is visible feedback in normal mode too — the
 * StatusBar pill and log viewer are dev-/monitor-only and absent on /recordings.
 * The dataset is written under <output_dir>/_lerobot_exports/<name>/.
 */

import { CheckCircle2, Loader2, XCircle } from "lucide-react";
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
function MappingInfo({ config, loading }: { config: LeRobotConfigResponse | undefined; loading: boolean }) {
  if (loading) return <div className="text-sm text-muted-foreground">Loading…</div>;
  if (!config?.configured) {
    return (
      <div className="text-sm text-muted-foreground">
        No <code>lerobot_export</code> mapping in the active robot config. Add one to the robot's YAML to enable export.
      </div>
    );
  }
  return (
    <div className="text-sm text-muted-foreground">
      {config.robot_type} · cameras: {config.cameras.join(", ") || "(none)"}
    </div>
  );
}

/** Live progress / result of the running export job. */
function ExportProgress({ job, outputName }: { job: JobSchema | undefined; outputName: string }) {
  if (job?.status === "completed") {
    return (
      <div className="flex items-start gap-2 text-sm">
        <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-green-500" />
        <span>
          Export completed: <code>_lerobot_exports/{outputName}/</code>
        </span>
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
  const { data: config, isLoading: configLoading } = useLeRobotConfig();
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

  const configured = config?.configured ?? false;
  const canSubmit = configured && outputName.trim() !== "" && folders.length > 0 && !mutation.isPending;

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

  // While running, "Close" only dismisses the dialog (the job keeps running and
  // re-appears on reopen). On success it also clears the recording selection.
  const handleClose = () => {
    if (job?.status === "completed") onExported();
    else onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
                <MappingInfo config={config} loading={configLoading} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lerobot-output">Output name</Label>
                <Input
                  id="lerobot-output"
                  value={outputName}
                  onChange={(e) => setOutputName(e.target.value)}
                  placeholder="e.g. pick_and_place_v1"
                  disabled={!configured}
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
