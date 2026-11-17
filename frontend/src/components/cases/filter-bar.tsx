"use client";

import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { automationLabel, priorityLabel, typeLabel } from "@/lib/labels";
import {
  AUTOMATION_STATUSES,
  CASE_TYPES,
  PRIORITIES,
  type AutomationStatus,
  type CaseType,
  type FieldValues,
  type Priority,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export interface Filters {
  q: string;
  tags: string[];
  priority: Priority[];
  type: CaseType[];
  automation_status: AutomationStatus[];
  /** Custom field name -> selected values. */
  fields: Record<string, string[]>;
}

export const emptyFilters: Filters = { q: "", tags: [], priority: [], type: [], automation_status: [], fields: {} };

const fieldFilterCount = (f: Filters) => Object.values(f.fields).reduce((n, v) => n + v.length, 0);

export const isFiltered = (f: Filters) =>
  !!f.q.trim() ||
  f.tags.length + f.priority.length + f.type.length + f.automation_status.length + fieldFilterCount(f) > 0;

export function FilterBar({
  value,
  onChange,
  tags,
  fields = [],
}: {
  value: Filters;
  onChange: (f: Filters) => void;
  tags: string[];
  fields?: FieldValues[];
}) {
  // Debounce the search box; other filters apply immediately.
  const [q, setQ] = useState(value.q);
  useEffect(() => setQ(value.q), [value.q]);
  useEffect(() => {
    if (q === value.q) return;
    const t = setTimeout(() => onChange({ ...value, q }), 250);
    return () => clearTimeout(t);
  }, [q, value, onChange]);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative w-64">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search title or C123…"
          className="h-8 pl-8"
          aria-label="Search cases"
        />
      </div>
      <MultiSelect
        label="Priority"
        options={PRIORITIES.map((p) => [p, priorityLabel[p]])}
        value={value.priority}
        onChange={(priority) => onChange({ ...value, priority })}
      />
      <MultiSelect
        label="Type"
        options={CASE_TYPES.map((t) => [t, typeLabel[t]])}
        value={value.type}
        onChange={(type) => onChange({ ...value, type })}
      />
      <MultiSelect
        label="Automation"
        options={AUTOMATION_STATUSES.map((a) => [a, automationLabel[a]])}
        value={value.automation_status}
        onChange={(automation_status) => onChange({ ...value, automation_status })}
      />
      <MultiSelect
        label="Tags"
        options={tags.map((t) => [t, t])}
        value={value.tags}
        onChange={(t) => onChange({ ...value, tags: t })}
        emptyText="No tags in this project"
      />
      {fields.length > 0 && (
        <FieldsFilter options={fields} value={value.fields} onChange={(f) => onChange({ ...value, fields: f })} />
      )}
      {isFiltered(value) && (
        <Button variant="ghost" size="sm" onClick={() => onChange(emptyFilters)}>
          <X /> Clear
        </Button>
      )}
    </div>
  );
}

function MultiSelect<T extends string>({
  label,
  options,
  value,
  onChange,
  emptyText = "No options",
}: {
  label: string;
  options: [T, string][];
  value: T[];
  onChange: (v: T[]) => void;
  emptyText?: string;
}) {
  const active = value.length > 0;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn("gap-1", active && "border-primary/50 bg-primary/5")}
        >
          {label}
          {active && (
            <span className="rounded bg-primary px-1 text-[10px] text-primary-foreground">{value.length}</span>
          )}
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="max-h-72 w-52 overflow-y-auto p-1">
        {options.length === 0 && <p className="p-2 text-sm text-muted-foreground">{emptyText}</p>}
        {options.map(([v, text]) => {
          const checked = value.includes(v);
          return (
            <label
              key={v}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted"
            >
              <Checkbox
                checked={checked}
                onCheckedChange={() => onChange(checked ? value.filter((x) => x !== v) : [...value, v])}
              />
              {text}
            </label>
          );
        })}
      </PopoverContent>
    </Popover>
  );
}

function FieldsFilter({
  options,
  value,
  onChange,
}: {
  options: FieldValues[];
  value: Record<string, string[]>;
  onChange: (v: Record<string, string[]>) => void;
}) {
  const active = Object.values(value).reduce((n, v) => n + v.length, 0);
  const [field, setField] = useState<string>(() => Object.keys(value)[0] ?? options[0]?.name ?? "");
  const [needle, setNeedle] = useState("");
  const current = options.find((o) => o.name === field);
  const selected = value[field] ?? [];
  const toggle = (v: string) => {
    const next = selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v];
    const copy = { ...value };
    if (next.length) copy[field] = next;
    else delete copy[field];
    onChange(copy);
  };
  const shown = (current?.values ?? []).filter((v) => v.toLowerCase().includes(needle.trim().toLowerCase()));

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className={cn("gap-1", active && "border-primary/50 bg-primary/5")}>
          Fields
          {active > 0 && <span className="rounded bg-primary px-1 text-[10px] text-primary-foreground">{active}</span>}
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="grid w-72 gap-2 p-2">
        <Select value={field} onValueChange={(f) => { setField(f); setNeedle(""); }}>
          <SelectTrigger size="sm" className="w-full" aria-label="Field">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.name} value={o.name}>
                {o.name}
                {value[o.name]?.length ? ` (${value[o.name].length})` : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {(current?.values.length ?? 0) > 8 && (
          <Input value={needle} onChange={(e) => setNeedle(e.target.value)} placeholder="Find a value…" className="h-8" />
        )}
        <div className="max-h-60 overflow-y-auto">
          {shown.length === 0 && <p className="p-2 text-sm text-muted-foreground">No values</p>}
          {shown.map((v) => (
            <label key={v} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted">
              <Checkbox checked={selected.includes(v)} onCheckedChange={() => toggle(v)} />
              <span className="min-w-0 truncate">{v}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
