/** Dialog for editing task_name / tags / master-defined metadata.
 *
 * Provides chip-style tag input (commit with Enter / Tab / Comma; Backspace removes the trailing tag),
 * a single-line task_name input, and one control per master-defined metadata field (a select for
 * `select` fields, a text input for `number` / `text`). recording_config_name is fixed at recording
 * time and is not editable; it is shown for reference only.
 */

import { ChevronDown, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { FileEntry } from "@/api/generated/schemas";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useConfig, useUpdateRecordingMeta } from "@/hooks/use-api";
import { useAddLog } from "@/hooks/use-topics-stream";
import { matchesPattern } from "@/lib/metadata-field";

export function MetaEditDialog({
  entry,
  open,
  onOpenChange,
}: {
  entry: FileEntry;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  // --- Server state ---
  const mutation = useUpdateRecordingMeta();
  const addLog = useAddLog();
  const { data: config } = useConfig();
  const fields = config?.metadata_fields ?? [];

  // --- Local editing state (initialized from entry each time the dialog opens) ---
  const [taskName, setTaskName] = useState(entry.task_name ?? "");
  const [tags, setTags] = useState<string[]>(entry.tags);
  const [tagDraft, setTagDraft] = useState("");
  const [metadata, setMetadata] = useState<Record<string, string>>(entry.metadata);

  useEffect(() => {
    if (open) {
      setTaskName(entry.task_name ?? "");
      setTags(entry.tags);
      setTagDraft("");
      setMetadata(entry.metadata);
    }
  }, [open, entry.task_name, entry.tags, entry.metadata]);

  const commitTagDraft = () => {
    const trimmed = tagDraft.trim();
    if (trimmed && !tags.includes(trimmed)) {
      setTags([...tags, trimmed]);
    }
    setTagDraft("");
  };

  const handleSave = () => {
    // Include the in-progress tag draft as well
    const finalTags = (() => {
      const trimmed = tagDraft.trim();
      if (trimmed && !tags.includes(trimmed)) return [...tags, trimmed];
      return tags;
    })();

    mutation.mutate(
      {
        name: entry.name,
        data: {
          task_name: taskName.trim() === "" ? null : taskName.trim(),
          tags: finalTags,
          metadata,
        },
      },
      {
        onSuccess: () => {
          addLog("info", `Updated metadata: ${entry.name}`);
          onOpenChange(false);
        },
        onError: (err: unknown) => {
          const msg = err instanceof Error ? err.message : "Update failed";
          addLog("danger", `Failed to update metadata (${entry.name}): ${msg}`);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent onClick={(e) => e.stopPropagation()}>
        <DialogHeader>
          <DialogTitle>Edit metadata</DialogTitle>
          <DialogDescription>{entry.name}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* task_name */}
          <div className="space-y-1.5">
            <Label htmlFor="meta-task-name">Task name</Label>
            <Input
              id="meta-task-name"
              value={taskName}
              onChange={(e) => setTaskName(e.target.value)}
              placeholder="e.g. pick-and-place"
              autoFocus
            />
          </div>

          {/* tags (chip-style) */}
          <div className="space-y-1.5">
            <Label htmlFor="meta-tags">Tags</Label>
            <div className="flex flex-wrap items-center gap-1.5 rounded-md border border-input bg-transparent px-2 py-1.5">
              {tags.map((tag) => (
                <Badge key={tag} variant="secondary" className="gap-1">
                  {tag}
                  <button
                    type="button"
                    onClick={() => setTags(tags.filter((t) => t !== tag))}
                    className="text-muted-foreground hover:text-foreground"
                    aria-label={`Remove ${tag}`}
                  >
                    <X size={12} />
                  </button>
                </Badge>
              ))}
              <input
                id="meta-tags"
                className="flex-1 min-w-[80px] bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                value={tagDraft}
                onChange={(e) => setTagDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === "Tab" || e.key === ",") {
                    e.preventDefault();
                    commitTagDraft();
                  } else if (e.key === "Backspace" && tagDraft === "" && tags.length > 0) {
                    setTags(tags.slice(0, -1));
                  }
                }}
                onBlur={commitTagDraft}
                placeholder={tags.length === 0 ? "Type a tag and press Enter" : ""}
              />
            </div>
          </div>

          {/* master-defined metadata fields */}
          {fields.map((field) => {
            const value = metadata[field.key] ?? "";
            // Set (or clear, when empty) a single field, keeping the rest.
            const setValue = (v: string) => {
              const next = { ...metadata };
              if (v === "") delete next[field.key];
              else next[field.key] = v;
              setMetadata(next);
            };
            return (
              <div key={field.key} className="space-y-1.5">
                <Label htmlFor={`meta-field-${field.key}`}>{field.label}</Label>
                {field.type === "select" ? (
                  <div className="relative">
                    <select
                      id={`meta-field-${field.key}`}
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                      className="w-full appearance-none rounded-md border border-input bg-transparent py-2 pr-8 pl-3 text-sm text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      <option value="">—</option>
                      {field.options.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    <ChevronDown
                      size={14}
                      className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground"
                    />
                  </div>
                ) : (
                  <Input
                    id={`meta-field-${field.key}`}
                    inputMode={field.type === "number" ? "numeric" : undefined}
                    value={value}
                    placeholder={field.placeholder ?? undefined}
                    aria-invalid={!matchesPattern(field.pattern, value)}
                    onChange={(e) => {
                      // Number fields accept digits only, kept as a string so leading zeros survive.
                      if (field.type === "number" && !/^[0-9]*$/.test(e.target.value)) return;
                      setValue(e.target.value);
                    }}
                  />
                )}
              </div>
            );
          })}

          {/* recording_config_name (read-only) */}
          {entry.recording_config_name && (
            <div className="space-y-1.5">
              <Label>Recording config (fixed at recording time)</Label>
              <div className="text-sm text-muted-foreground">{entry.recording_config_name}</div>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave} disabled={mutation.isPending}>
            {mutation.isPending ? "Saving..." : "Save"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
