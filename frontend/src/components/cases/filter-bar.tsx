"use client";

import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { automationLabel, priorityLabel, typeLabel } from "@/lib/labels";
import {
  AUTOMATION_STATUSES,
  CASE_TYPES,
  PRIORITIES,
  type AutomationStatus,
  type CaseType,
  type Priority,
} from "@/lib/types";
import { cn } from "@/lib/utils";

export interface Filters {
  q: string;
  tags: string[];
  priority: Priority[];
  type: CaseType[];
  automation_status: AutomationStatus[];
}

export const emptyFilters: Filters = { q: "", tags: [], priority: [], type: [], automation_status: [] };

export const isFiltered = (f: Filters) =>
  !!f.q.trim() || f.tags.length + f.priority.length + f.type.length + f.automation_status.length > 0;

export function FilterBar({
  value,
  onChange,
  tags,
}: {
  value: Filters;
  onChange: (f: Filters) => void;
  tags: string[];
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
