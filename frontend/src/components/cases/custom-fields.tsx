"use client";

import { Plus, X } from "lucide-react";
import { Combobox } from "@/components/combobox";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CustomField, FieldValues } from "@/lib/types";

const URL_RE = /^https?:\/\/\S+$/i;

export function CustomFieldsView({ fields }: { fields: CustomField[] }) {
  if (!fields.length) return null;
  return (
    <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-6 gap-y-1.5 text-sm" data-testid="custom-fields">
      {fields.map((f) => (
        <div key={f.name} className="contents">
          <dt className="text-muted-foreground">{f.name}</dt>
          <dd className="min-w-0 break-words whitespace-pre-wrap">
            {URL_RE.test(f.value) ? (
              <a href={f.value} target="_blank" rel="noreferrer noopener" className="text-primary underline">
                {f.value}
              </a>
            ) : (
              f.value
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function CustomFieldsEditor({
  value,
  onChange,
  known = [],
}: {
  value: CustomField[];
  onChange: (fields: CustomField[]) => void;
  /** Field names/values used elsewhere in the project, for pickers. */
  known?: FieldValues[];
}) {
  const set = (i: number, patch: Partial<CustomField>) =>
    onChange(value.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const unusedNames = (i: number) =>
    known
      .map((k) => k.name)
      .filter((n) => !value.some((f, j) => j !== i && f.name.trim().toLowerCase() === n.toLowerCase()));
  return (
    <div className="grid gap-2" data-testid="custom-fields-editor">
      {value.map((f, i) => {
        const values = known.find((k) => k.name.toLowerCase() === f.name.trim().toLowerCase())?.values ?? [];
        return (
          <div key={i} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_auto] gap-2">
            <Combobox
              aria-label={`Field ${i + 1} name`}
              value={f.name || null}
              onChange={(name) => set(i, { name: name ?? "" })}
              options={unusedNames(i)}
              placeholder="Field name"
              searchPlaceholder="Find a field"
              creatable
              clearable={false}
            />
            {values.length > 0 ? (
              <Combobox
                aria-label={`Field ${i + 1} value`}
                value={f.value || null}
                onChange={(v) => set(i, { value: v ?? "" })}
                options={values}
                placeholder="Value"
                searchPlaceholder="Find a value"
                creatable
              />
            ) : (
              <Input
                value={f.value}
                onChange={(e) => set(i, { value: e.target.value })}
                placeholder="Value"
                aria-label={`Field ${i + 1} value`}
              />
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => onChange(value.filter((_, j) => j !== i))}
              aria-label={`Remove field ${f.name || i + 1}`}
            >
              <X />
            </Button>
          </div>
        );
      })}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="justify-self-start"
        onClick={() => onChange([...value, { name: "", value: "" }])}
      >
        <Plus /> Add field
      </Button>
    </div>
  );
}
