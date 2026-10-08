/** Dialog for applying master-defined `select` metadata to several recordings at once.
 *
 * Fields start empty ("Unchanged"); only the fields given a value are applied, the rest stay as they are.
 */

import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useBulkUpdateRecordingMeta, useConfig } from "@/hooks/use-api";
import { useAddLog } from "@/hooks/use-topics-stream";
import { MetadataFieldInput } from "./metadata-field-input";

export function BulkMetaEditDialog({
  folders,
  open,
  onOpenChange,
  onSaved,
}: {
  folders: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  // --- Server state ---
  const mutation = useBulkUpdateRecordingMeta();
  const addLog = useAddLog();
  const { data: config } = useConfig();
  const selectFields = (config?.metadata_fields ?? []).filter((f) => f.type === "select");

  // --- Local editing state (reset each time the dialog opens) ---
  const [changes, setChanges] = useState<Record<string, string>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setChanges({});
      setErrorMessage(null);
    }
  }, [open]);

  const handleSave = () => {
    setErrorMessage(null);
    mutation.mutate(
      { data: { folders, metadata: changes } },
      {
        onSuccess: () => {
          addLog("info", `Updated metadata of ${folders.length} recording${folders.length === 1 ? "" : "s"}`);
          onOpenChange(false);
          onSaved();
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Update failed";
          setErrorMessage(msg);
          addLog("danger", `Failed to update metadata: ${msg}`);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Edit metadata</DialogTitle>
          <DialogDescription>
            {folders.length} recording{folders.length === 1 ? "" : "s"} selected. Fields left as Unchanged keep their
            current values.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-1 space-y-4">
          {selectFields.map((field) => (
            <MetadataFieldInput
              key={field.key}
              field={field}
              value={changes[field.key] ?? ""}
              emptyLabel="Unchanged"
              onChange={(v) => {
                const next = { ...changes };
                if (v === "") delete next[field.key];
                else next[field.key] = v;
                setChanges(next);
              }}
            />
          ))}
        </div>

        {errorMessage && (
          <p className="text-[13px] text-red-600 dark:text-red-400">Failed to update metadata: {errorMessage}</p>
        )}

        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave} disabled={mutation.isPending || Object.keys(changes).length === 0}>
            {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
            Save to {folders.length} recording{folders.length === 1 ? "" : "s"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
