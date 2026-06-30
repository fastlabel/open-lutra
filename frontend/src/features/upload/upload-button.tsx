/** Upload action button shown in the recording-detail header.
 *
 * Stateful label that reflects the current upload phase
 * (Upload / Uploading N% / Re-upload / Retry) and shows the failure
 * message inline when the last attempt failed. Driven by
 * `useUploadStatus(folderPath)`; clicks fire `POST /api/upload/start`
 * which always overwrites the previously uploaded object (per issue #6).
 *
 * Rendered disabled with an explanatory tooltip when `upload_enabled` is
 * false on `/api/config` (no upload destination configured), so the operator
 * can still discover the feature and learn it needs to be set up.
 */

import { AlertCircle, CloudCheck, CloudUpload, Loader2 } from "lucide-react";
import type { ComponentType } from "react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useConfig, useStartUpload } from "@/hooks/use-api";
import { type UploadStatus, useUploadStatus } from "@/hooks/use-upload-status";

type IconComponent = ComponentType<{ size?: number; className?: string }>;

function buildLabel(
  status: UploadStatus,
  percent: number | null,
): { Icon: IconComponent; text: string; spin?: boolean } {
  switch (status) {
    case "uploading":
      return { Icon: Loader2, text: percent === null ? "Uploading…" : `Uploading ${percent}%`, spin: true };
    case "uploaded":
      return { Icon: CloudCheck, text: "Re-upload" };
    case "failed":
      return { Icon: AlertCircle, text: "Retry upload" };
    default:
      return { Icon: CloudUpload, text: "Upload" };
  }
}

export function UploadButton({ folderPath }: { folderPath: string }) {
  // --- Server state ---
  const { data: config } = useConfig();
  const { status, percent, error } = useUploadStatus(folderPath);
  const { mutate: startUpload, isPending } = useStartUpload();

  if (!config?.upload_enabled) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          {/* The disabled button has pointer-events:none, so wrap it in a span
              that receives the hover the tooltip needs to open. */}
          <span className="cursor-not-allowed">
            <Button type="button" size="sm" variant="outline" disabled>
              <CloudUpload size={14} />
              <span>Upload</span>
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom">No upload destination is configured</TooltipContent>
      </Tooltip>
    );
  }

  const disabled = status === "uploading" || isPending;
  const { Icon, text, spin } = buildLabel(status, percent);
  const failed = status === "failed";

  return (
    <div className="flex items-center gap-2">
      <Button
        type="button"
        size="sm"
        variant={failed ? "destructive" : "outline"}
        disabled={disabled}
        onClick={() => startUpload({ params: { path: folderPath } })}
        title={failed ? (error ?? "Upload failed") : text}
      >
        <Icon size={14} className={spin ? "animate-spin" : undefined} />
        <span>{text}</span>
      </Button>
      {failed && error && (
        <span className="max-w-[18rem] truncate text-[13px] text-red-300" title={error}>
          {error}
        </span>
      )}
    </div>
  );
}
