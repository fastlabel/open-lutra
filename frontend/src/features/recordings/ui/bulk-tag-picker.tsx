/** Tri-state tag checklist for the bulk edit dialog, with an input that adds a tag to the list.
 *
 * Each row shows on how many of the selected recordings the tag is present and, once changed, what saving will do
 * to it. The input commits on Enter / Tab / comma, like the tag field of the single-recording dialog. The draft is
 * owned by the caller so that Save can include a tag that was typed but not committed yet.
 */

import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { type TagRow, tagDelta } from "../bulk-tags";

export function BulkTagPicker({
  rows,
  total,
  draft,
  onDraftChange,
  onToggle,
  onAdd,
}: {
  rows: TagRow[];
  /** Number of selected recordings, the denominator of each row's count. */
  total: number;
  draft: string;
  onDraftChange: (draft: string) => void;
  onToggle: (tag: string) => void;
  onAdd: (tag: string) => void;
}) {
  const commitDraft = () => {
    const trimmed = draft.trim();
    if (trimmed) onAdd(trimmed);
    onDraftChange("");
  };

  return (
    <div className="space-y-2">
      <div className="max-h-60 overflow-auto rounded-md border border-input">
        {rows.length === 0 && (
          <p className="px-3 py-2 text-[13px] text-muted-foreground">No tags on the selected recordings yet.</p>
        )}
        {rows.map((row) => {
          const delta = tagDelta(row);
          const id = `bulk-tag-${encodeURIComponent(row.tag)}`;
          return (
            <div
              key={row.tag}
              className={cn(
                "flex items-center gap-2.5 border-b border-input px-3 py-1.5 last:border-b-0",
                delta === "add" && "bg-primary/10",
                delta === "remove" && "bg-destructive/10",
              )}
            >
              <Checkbox
                id={id}
                checked={row.check === "mixed" ? "indeterminate" : row.check === "checked"}
                onCheckedChange={() => onToggle(row.tag)}
              />
              <Label
                htmlFor={id}
                className={cn(
                  "min-w-0 flex-1 cursor-pointer truncate font-normal",
                  delta === "remove" && "text-muted-foreground line-through",
                )}
              >
                {row.tag}
              </Label>
              <span className="text-[13px] text-muted-foreground tabular-nums">
                {row.count}/{total}
              </span>
              {delta && (
                <span className={cn("text-[13px]", delta === "add" ? "text-primary" : "text-destructive")}>
                  {delta === "add" ? "→ add to all" : "→ remove from all"}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <Input
        value={draft}
        placeholder="Add a tag and press Enter"
        aria-label="Add a tag"
        onChange={(e) => onDraftChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key !== "Enter" && e.key !== "Tab" && e.key !== ",") return;
          // An empty Tab keeps moving focus; anything else commits the draft instead.
          if (e.key === "Tab" && draft.trim() === "") return;
          e.preventDefault();
          commitDraft();
        }}
        onBlur={commitDraft}
      />
    </div>
  );
}
