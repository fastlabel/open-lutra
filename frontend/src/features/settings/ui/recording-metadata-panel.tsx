/** Popover panel for setting pre-registered metadata before recording.
 *
 * Reads the master-defined fields from the recording config and renders one
 * control per field — a select for `select` fields, a text input for `number`
 * (digits only, kept as a string) and `text` fields. Values are stored in the
 * settings store (persisted to localStorage), so they stick across recordings
 * until changed — like the task name. Renders nothing when the config defines
 * no metadata fields.
 */

import { ChevronDown, Tags } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useConfig } from "@/hooks/use-api";
import { matchesPattern } from "@/lib/metadata-field";
import { useSettingsStore } from "../store";

export function RecordingMetadataPanel() {
  // --- Server state ---
  const { data: config } = useConfig();
  const fields = config?.metadata_fields ?? [];

  // --- Render-only state ---
  const metadata = useSettingsStore((s) => s.metadata);
  const update = useSettingsStore((s) => s.update);

  if (fields.length === 0) return null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-1 text-[13px] text-foreground hover:bg-muted"
        >
          <Tags size={14} />
          <span>
            Metadata {fields.filter((f) => metadata[f.key]).length}/{fields.length}
          </span>
          <ChevronDown size={13} className="text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-3">
        <div className="flex flex-col gap-3">
          {fields.map((field) => {
            const value = metadata[field.key] ?? "";
            // Set (or clear, when empty) a single field, keeping the rest.
            const setValue = (v: string) => {
              const next = { ...metadata };
              if (v === "") delete next[field.key];
              else next[field.key] = v;
              update({ metadata: next });
            };
            const invalid = !matchesPattern(field.pattern, value);
            const controlId = `meta-panel-${field.key}`;
            return (
              <div key={field.key} className="flex flex-col gap-1 text-[13px] text-muted-foreground">
                <label htmlFor={controlId}>{field.label}</label>
                {field.type === "select" ? (
                  <div className="relative">
                    <select
                      id={controlId}
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                      className="w-full appearance-none rounded-md border border-border bg-transparent py-1 pr-6 pl-2 text-[13px] text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      <option value="">—</option>
                      {field.options.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    <ChevronDown
                      size={13}
                      className="pointer-events-none absolute top-1/2 right-1.5 -translate-y-1/2 text-muted-foreground"
                    />
                  </div>
                ) : (
                  <input
                    id={controlId}
                    type="text"
                    inputMode={field.type === "number" ? "numeric" : undefined}
                    value={value}
                    placeholder={field.placeholder ?? undefined}
                    aria-invalid={invalid}
                    onChange={(e) => {
                      // Number fields accept digits only, kept as a string so leading zeros survive.
                      if (field.type === "number" && !/^[0-9]*$/.test(e.target.value)) return;
                      setValue(e.target.value);
                    }}
                    className={`w-full rounded-md border bg-transparent px-2 py-1 text-[13px] text-foreground focus:outline-none focus:ring-1 ${
                      invalid ? "border-destructive focus:ring-destructive/50" : "border-border focus:ring-ring"
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
