"use client";

import { Plus, X } from "lucide-react";
import { useId } from "react";

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
  /** Field names/values used elsewhere in the project, for autocomplete. */
  known?: FieldValues[];
}) {
  const id = useId();
  const set = (i: number, patch: Partial<CustomField>) =>
    onChange(value.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  return (
    <div className="grid gap-2" data-testid="custom-fields-editor">
      {value.map((f, i) => {
        const values = known.find((k) => k.name.toLowerCase() === f.name.trim().toLowerCase())?.values ?? [];
        return (
          <div key={i} className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_auto] gap-2">
            <Input
              value={f.name}
              onChange={(e) => set(i, { name: e.target.value })}
              placeholder="Field, e.g. Sprint"
              list={`${id}-names`}
              aria-label={`Field ${i + 1} name`}
            />
            <Input
              value={f.value}
              onChange={(e) => set(i, { value: e.target.value })}
              placeholder="Value"
              list={`${id}-values-${i}`}
              aria-label={`Field ${i + 1} value`}
            />
            <datalist id={`${id}-values-${i}`}>
              {values.map((v) => (
                <option key={v} value={v} />
              ))}
            </datalist>
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
      <datalist id={`${id}-names`}>
        {known
          .filter((k) => !value.some((f) => f.name.trim().toLowerCase() === k.name.toLowerCase()))
          .map((k) => (
            <option key={k.name} value={k.name} />
          ))}
      </datalist>
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
