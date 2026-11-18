"use client";

import { ChevronDown, Plus, Settings2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/** Pick roles from the project's list; a role typed in the search box can be added too
 * (it joins the project list when the case is saved). */
export function RolePicker({
  id,
  value,
  onChange,
  options,
  projectId,
  placeholder = "Choose roles…",
}: {
  id?: string;
  value: string[];
  onChange: (roles: string[]) => void;
  options: string[];
  projectId: number;
  placeholder?: string;
}) {
  const [needle, setNeedle] = useState("");
  const lower = (s: string) => s.toLowerCase();
  const has = (list: string[], r: string) => list.some((x) => lower(x) === lower(r));
  const all = [...options, ...value.filter((r) => !has(options, r))];
  const query = needle.trim().replace(/\s+/g, " ");
  const shown = all.filter((r) => lower(r).includes(lower(query)));
  const toggle = (r: string) => onChange(has(value, r) ? value.filter((x) => lower(x) !== lower(r)) : [...value, r]);
  const addTyped = () => {
    if (query && !has(all, query)) onChange([...value, query]);
    else if (query) {
      const existing = all.find((r) => lower(r) === lower(query))!;
      if (!has(value, existing)) onChange([...value, existing]);
    }
    setNeedle("");
  };

  return (
    <Popover onOpenChange={(o) => !o && setNeedle("")}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          className={cn(
            "flex min-h-9 w-full flex-wrap items-center gap-1 rounded-md border px-2 py-1 text-left text-sm",
            "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
          )}
        >
          {value.length === 0 && <span className="px-1 text-muted-foreground">{placeholder}</span>}
          {value.map((r) => (
            <span key={r} className="inline-flex items-center gap-0.5 rounded bg-muted px-1.5 py-0.5 text-xs">
              {r}
              <span
                role="button"
                tabIndex={-1}
                aria-label={`Remove role ${r}`}
                className="text-muted-foreground hover:text-foreground"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(r);
                }}
              >
                <X className="size-3" />
              </span>
            </span>
          ))}
          <ChevronDown className="ml-auto size-3.5 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="grid w-72 gap-1 p-1">
        <Input
          value={needle}
          onChange={(e) => setNeedle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addTyped();
            }
          }}
          placeholder="Find or add a role…"
          aria-label="Find or add a role"
          className="h-8"
        />
        <div className="max-h-60 overflow-y-auto" role="group" aria-label="Roles">
          {shown.map((r) => (
            <label key={r} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted">
              <Checkbox checked={has(value, r)} onCheckedChange={() => toggle(r)} />
              <span className="min-w-0 truncate">{r}</span>
            </label>
          ))}
          {all.length === 0 && !query && (
            <p className="px-2 py-1.5 text-sm text-muted-foreground">No roles in this project yet. Type one above.</p>
          )}
        </div>
        {query && !has(all, query) && (
          <Button type="button" variant="ghost" size="sm" className="justify-start" onClick={addTyped}>
            <Plus /> Add “{query}”
          </Button>
        )}
        <Link
          href={`/projects/${projectId}/settings`}
          className="flex items-center gap-1.5 border-t px-2 pt-1.5 pb-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <Settings2 className="size-3.5" /> Manage project roles
        </Link>
      </PopoverContent>
    </Popover>
  );
}
