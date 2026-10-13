/** Dialog for editing tags and master-defined `select` metadata on several recordings at once.
 *
 * Tags present on the selection are listed with a tri-state checkbox (on all / on some / on none): checking a tag
 * adds it to every selected recording and unchecking removes it from every one. Select fields start as "Unchanged".
 * Only what the operator changed is sent; everything else keeps its current value on each recording. A tag still
 * being typed counts as added, so Save behaves the same whether or not the operator pressed Enter first.
 */

import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useBulkUpdateRecordingMeta, useConfig, useFiles } from "@/hooks/use-api";
import { useAddLog } from "@/hooks/use-topics-stream";
import { buildTagRows, cycleTagCheck, newTagRow, type TagCheck, tagRequest, withTagChecked } from "../bulk-tags";
import { BulkTagPicker } from "./bulk-tag-picker";
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
  const { data: files } = useFiles();
  const initialRows = useMemo(
    () =>
      buildTagRows(
        (files?.entries ?? []).filter((entry) => folders.includes(entry.name)),
        folders.length,
      ),
    [files, folders],
  );

  // --- Local editing state (reset each time the dialog opens) ---
  // Tag edits are kept apart from the rows derived from the server so a background refetch cannot discard them.
  const [tagChecks, setTagChecks] = useState<Record<string, TagCheck>>({});
  const [newTags, setNewTags] = useState<string[]>([]);
  const [tagDraft, setTagDraft] = useState("");
  const [changes, setChanges] = useState<Record<string, string>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTagChecks({});
      setNewTags([]);
      setTagDraft("");
      setChanges({});
      setErrorMessage(null);
    }
  }, [open]);

  const tagRows = useMemo(
    () => [
      ...initialRows.map((row) => ({
        ...row,
        check: tagChecks[row.tag] ?? row.check,
      })),
      ...newTags.map((tag) => ({
        ...newTagRow(tag),
        check: tagChecks[tag] ?? "checked",
      })),
    ],
    [initialRows, newTags, tagChecks],
  );
  const draftTag = tagDraft.trim();
  const { add_tags, remove_tags } = tagRequest(draftTag ? withTagChecked(tagRows, draftTag) : tagRows);
  const hasChanges = add_tags.length + remove_tags.length + Object.keys(changes).length > 0;

  // --- Event handlers ---
  const handleSave = () => {
    setErrorMessage(null);
    mutation.mutate(
      { data: { folders, metadata: changes, add_tags, remove_tags } },
      {
        onSuccess: () => {
          addLog("info", `Updated ${folders.length} recording${folders.length === 1 ? "" : "s"}`);
          onOpenChange(false);
          onSaved();
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Update failed";
          setErrorMessage(msg);
          addLog("danger", `Failed to update recordings: ${msg}`);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Edit tags and metadata</DialogTitle>
          <DialogDescription>
            {folders.length} recording{folders.length === 1 ? "" : "s"} selected. Tags and fields left unchanged keep
            their current values.
          </DialogDescription>
        </DialogHeader>

        <div className="mt-1 space-y-5">
          <section className="space-y-2">
            <h3 className="text-[13px] font-medium tracking-wide text-muted-foreground uppercase">Tags</h3>
            <BulkTagPicker
              rows={tagRows}
              total={folders.length}
              draft={tagDraft}
              onDraftChange={setTagDraft}
              onToggle={(tag) => {
                const row = tagRows.find((r) => r.tag === tag);
                if (row) setTagChecks({ ...tagChecks, [tag]: cycleTagCheck(row) });
              }}
              onAdd={(tag) =>
                tagRows.some((r) => r.tag === tag)
                  ? setTagChecks({ ...tagChecks, [tag]: "checked" })
                  : setNewTags([...newTags, tag])
              }
            />
          </section>

          {selectFields.length > 0 && (
            <section className="space-y-4">
              <h3 className="text-[13px] font-medium tracking-wide text-muted-foreground uppercase">Metadata</h3>
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
            </section>
          )}
        </div>

        {errorMessage && <p className="text-[13px] text-red-400">Failed to update recordings: {errorMessage}</p>}

        <div className="flex justify-end gap-2 pt-3">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave} disabled={mutation.isPending || !hasChanges}>
            {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
            Save to {folders.length} recording{folders.length === 1 ? "" : "s"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
