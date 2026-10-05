/** Input control for one master-defined metadata field: a select for `select` fields, a text input for `number` / `text`. */

import { ChevronDown } from "lucide-react";
import type { MetadataFieldResponse } from "@/api/generated/schemas";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { matchesPattern } from "@/lib/metadata-field";

export function MetadataFieldInput({
  field,
  value,
  onChange,
  emptyLabel,
}: {
  field: MetadataFieldResponse;
  value: string;
  onChange: (value: string) => void;
  /** Label of the empty `select` option. */
  emptyLabel: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={`meta-field-${field.key}`}>{field.label}</Label>
      {field.type === "select" ? (
        <div className="relative">
          <select
            id={`meta-field-${field.key}`}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            className="w-full appearance-none rounded-md border border-input bg-transparent py-2 pr-8 pl-3 text-sm text-foreground cursor-pointer focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">{emptyLabel}</option>
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
            onChange(e.target.value);
          }}
        />
      )}
    </div>
  );
}
