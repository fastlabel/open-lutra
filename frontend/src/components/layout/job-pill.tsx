/** Compact in-progress job pill rendered in the StatusBar.
 *
 * Lights up while a quality / timeline / media / validation job is in the
 * queue or actively running. Used to give a single, always-visible signal
 * that background work (most importantly the auto-chained validation that
 * runs after every recording) is still in flight.
 */

import { Boxes, CheckCircle2, Film, Loader2, type LucideIcon, ShieldCheck, Sparkles } from "lucide-react";
import type { JobSchema } from "@/api/generated/schemas";

const JOB_TYPE_META: Record<string, { label: string; icon: LucideIcon }> = {
  quality: { label: "Quality", icon: Sparkles },
  timeline: { label: "Timeline", icon: Sparkles },
  media: { label: "Media", icon: Film },
  validation: { label: "Validation", icon: ShieldCheck },
  lerobot_export: { label: "LeRobot", icon: Boxes },
};

const FALLBACK_META = { label: "Job", icon: Sparkles };

export function JobPill({ job }: { job: JobSchema }) {
  const meta = JOB_TYPE_META[job.type] ?? FALLBACK_META;
  const Icon = meta.icon;
  const running = job.status === "running";
  const queued = job.status === "queued";
  const StatusIcon = running ? Loader2 : queued ? null : CheckCircle2;
  const progress = job.progress;
  const showProgress = running && progress.total > 1;

  return (
    <span
      data-testid={`job-pill-${job.type}`}
      className="inline-flex h-5 items-center gap-1 rounded border border-border bg-muted/40 px-1.5 text-[13px] text-muted-foreground"
      title={`${meta.label} · ${job.status}${job.folder ? ` · ${job.folder}` : ""}`}
    >
      <Icon size={11} className="shrink-0" />
      <span className="truncate max-w-[8rem]">{meta.label}</span>
      {StatusIcon && <StatusIcon size={11} className={`shrink-0 ${running ? "animate-spin" : ""}`} />}
      {showProgress && (
        <span className="tabular-nums">
          {progress.current}/{progress.total}
        </span>
      )}
    </span>
  );
}

/** Filter helper: keep jobs that are still doing work (queued or running). */
export function isInFlight(job: JobSchema): boolean {
  return job.status === "queued" || job.status === "running";
}
