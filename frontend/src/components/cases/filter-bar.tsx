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
import { automationLabel, complexityLabel, priorityLabel, progressLabel, stateLabel, typeLabel } from "@/lib/labels";
import {
  AUTOMATION_COMPLEXITIES,
  AUTOMATION_PROGRESSES,
  AUTOMATION_STATUSES,
  CASE_STATES,
  CASE_TYPES,
  PRIORITIES,
  type AutomationComplexity,
  type AutomationProgress,
  type AutomationStatus,
  type CaseFilter,
  type CaseState,
  type CaseType,
  type CaseValues,
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
  state: CaseState[];
  automation_complexity: AutomationComplexity[];
  automation_progress: AutomationProgress[];
  owner: string[];
  sprint: string[];
  roles: string[];
  /** Custom field name -> selected values. */
  fields: Record<string, string[]>;
}

export const emptyFilters: Filters = {
  q: "",
  tags: [],
  priority: [],
  type: [],
  automation_status: [],
  state: [],
  automation_complexity: [],
  automation_progress: [],
  owner: [],
  sprint: [],
  roles: [],
  fields: {},
};

/** Built-in fields filtered from the "Fields" popover (alongside custom fields). */
const BUILTIN = ["state", "owner", "sprint", "roles", "automation_progress", "automation_complexity"] as const;
type BuiltinKey = (typeof BUILTIN)[number];
const CUSTOM = "custom:";

const fieldFilterCount = (f: Filters) =>
  Object.values(f.fields).reduce((n, v) => n + v.length, 0) + BUILTIN.reduce((n, k) => n + f[k].length, 0);

export const isFiltered = (f: Filters) =>
  !!f.q.trim() ||
  f.tags.length + f.priority.length + f.type.length + f.automation_status.length + fieldFilterCount(f) > 0;

/** The API filter for the current filter bar state. */
export const toCaseFilter = (f: Filters): CaseFilter => ({
  q: f.q || undefined,
  tags: f.tags,
  priority: f.priority,
  type: f.type,
  automation_status: f.automation_status,
  state: f.state,
  automation_complexity: f.automation_complexity,
  automation_progress: f.automation_progress,
  owner: f.owner,
  sprint: f.sprint,
  roles: f.roles,
  fields: f.fields,
});

export function FilterBar({
  value,
  onChange,
  tags,
  fields = [],
  values,
}: {
  value: Filters;
  onChange: (f: Filters) => void;
  tags: string[];
  fields?: FieldValues[];
  values?: CaseValues;
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
      <FieldsFilter
        options={fieldOptions(fields, values)}
        value={{
          ...Object.fromEntries(BUILTIN.map((k) => [k, value[k] as string[]])),
          ...Object.fromEntries(Object.entries(value.fields).map(([k, v]) => [CUSTOM + k, v])),
        }}
        onChange={(sel) => {
          const next: Filters = { ...value, fields: {} };
          for (const k of BUILTIN) (next[k] as string[]) = sel[k] ?? [];
          for (const [k, v] of Object.entries(sel))
            if (k.startsWith(CUSTOM) && v.length) next.fields[k.slice(CUSTOM.length)] = v;
          onChange(next);
        }}
      />
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

interface FieldOption {
  key: string;
  label: string;
  values: [string, string][]; // [value, label]
}

const builtinLabel: Record<BuiltinKey, string> = {
  state: "State",
  owner: "Owner",
  sprint: "Sprint",
  roles: "Roles",
  automation_progress: "Automation progress",
  automation_complexity: "Automation complexity",
};

function fieldOptions(custom: FieldValues[], values?: CaseValues): FieldOption[] {
  const same = (xs: string[]): [string, string][] => xs.map((x) => [x, x]);
  const builtin: Record<BuiltinKey, [string, string][]> = {
    state: CASE_STATES.map((s) => [s, stateLabel[s]]),
    owner: same(values?.owners ?? []),
    sprint: same(values?.sprints ?? []),
    roles: same(values?.roles ?? []),
    automation_progress: AUTOMATION_PROGRESSES.map((a) => [a, progressLabel[a]]),
    automation_complexity: AUTOMATION_COMPLEXITIES.map((a) => [a, complexityLabel[a]]),
  };
  return [
    ...BUILTIN.map((k) => ({ key: k, label: builtinLabel[k], values: builtin[k] })),
    ...custom.map((f) => ({ key: CUSTOM + f.name, label: f.name, values: same(f.values) })),
  ];
}

function FieldsFilter({
  options,
  value,
  onChange,
}: {
  options: FieldOption[];
  value: Record<string, string[]>;
  onChange: (v: Record<string, string[]>) => void;
}) {
  const active = Object.values(value).reduce((n, v) => n + v.length, 0);
  const [field, setField] = useState<string>(
    () => Object.keys(value).find((k) => value[k].length) ?? options[0]?.key ?? "",
  );
  const [needle, setNeedle] = useState("");
  const current = options.find((o) => o.key === field);
  const selected = value[field] ?? [];
  const toggle = (v: string) => {
    const next = selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v];
    onChange({ ...value, [field]: next });
  };
  const shown = (current?.values ?? []).filter(([, label]) =>
    label.toLowerCase().includes(needle.trim().toLowerCase()),
  );

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
              <SelectItem key={o.key} value={o.key}>
                {o.label}
                {value[o.key]?.length ? ` (${value[o.key].length})` : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {(current?.values.length ?? 0) > 8 && (
          <Input value={needle} onChange={(e) => setNeedle(e.target.value)} placeholder="Find a value…" className="h-8" />
        )}
        <div className="max-h-60 overflow-y-auto">
          {shown.length === 0 && <p className="p-2 text-sm text-muted-foreground">No values</p>}
          {shown.map(([v, label]) => (
            <label key={v} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted">
              <Checkbox checked={selected.includes(v)} onCheckedChange={() => toggle(v)} />
              <span className="min-w-0 truncate">{label}</span>
            </label>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
