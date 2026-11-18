"use client";

import { Check, ChevronsUpDown, Plus, X } from "lucide-react";
import { useState } from "react";

import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const squash = (s: string) => s.trim().replace(/\s+/g, " ");
const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();
/** Case-insensitive substring match, keeping the list's own order. */
const matching = (list: string[], q: string) => (q ? list.filter((o) => o.toLowerCase().includes(q.toLowerCase())) : list);

const triggerClass =
  "flex min-h-9 w-full items-center gap-1 rounded-md border border-input bg-transparent px-3 py-1 text-left text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50 dark:bg-input/30";

/**
 * One value picked from a searchable list (like Jira's / Linear's property pickers).
 * With `creatable`, whatever is typed can be used as a new value.
 */
export function Combobox({
  id,
  value,
  onChange,
  options,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  creatable = false,
  clearable = true,
  "aria-label": ariaLabel,
  className,
}: {
  id?: string;
  value: string | null;
  onChange: (v: string | null) => void;
  options: string[];
  placeholder?: string;
  searchPlaceholder?: string;
  creatable?: boolean;
  clearable?: boolean;
  "aria-label"?: string;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const typed = squash(search);
  const all = value && !options.some((o) => same(o, value)) ? [value, ...options] : options;
  const shown = matching(all, typed);
  const pick = (v: string | null) => {
    onChange(v);
    setOpen(false);
    setSearch("");
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setSearch("");
      }}
      modal
    >
      <PopoverTrigger asChild>
        <button id={id} type="button" role="combobox" aria-expanded={open} aria-label={ariaLabel} className={cn(triggerClass, className)}>
          <span className={cn("min-w-0 flex-1 truncate", !value && "text-muted-foreground")}>{value || placeholder}</span>
          {clearable && value && (
            <span
              role="button"
              tabIndex={-1}
              aria-label="Clear"
              className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              onPointerDown={(e) => e.preventDefault()}
              onClick={(e) => {
                e.stopPropagation();
                onChange(null);
              }}
            >
              <X className="size-3.5" />
            </span>
          )}
          <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--radix-popover-trigger-width) min-w-56 p-0">
        <Command shouldFilter={false}>
          <CommandInput value={search} onValueChange={setSearch} placeholder={creatable ? `${searchPlaceholder} or type a new one` : searchPlaceholder} />
          <CommandList>
            {(!creatable || !typed) && shown.length === 0 && (
              <CommandEmpty>{creatable ? "Type to add." : "Nothing found."}</CommandEmpty>
            )}
            {shown.length > 0 && (
              <CommandGroup>
                {shown.map((o) => (
                  <CommandItem key={o} value={o} onSelect={() => pick(o)}>
                    <Check className={cn(value && same(value, o) ? "opacity-100" : "opacity-0")} />
                    <span className="truncate">{o}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {creatable && typed && !all.some((o) => same(o, typed)) && (
              <CommandGroup>
                <CommandItem value={`__create__${typed}`} onSelect={() => pick(typed)}>
                  <Plus /> Use “{typed}”
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Several values as chips, picked from a searchable list; the list stays open while
 * toggling. With `creatable`, Enter on a new text adds it.
 */
export function MultiCombobox({
  id,
  value,
  onChange,
  options,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  creatable = true,
  normalize = squash,
  noun = "item",
  footer,
  "aria-label": ariaLabel,
}: {
  id?: string;
  value: string[];
  onChange: (v: string[]) => void;
  options: string[];
  placeholder?: string;
  searchPlaceholder?: string;
  creatable?: boolean;
  /** Applied to typed values (e.g. lowercase tags). */
  normalize?: (s: string) => string;
  noun?: string;
  footer?: React.ReactNode;
  "aria-label"?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const has = (list: string[], v: string) => list.some((x) => same(x, v));
  const all = [...options, ...value.filter((v) => !has(options, v))];
  const typed = normalize(search);
  const shown = matching(all, squash(search));
  const toggle = (v: string) => onChange(has(value, v) ? value.filter((x) => !same(x, v)) : [...value, v]);
  const add = (raw: string) => {
    // "a, b, c" adds several at once
    const fresh = raw.split(",").map(normalize).filter(Boolean);
    const next = [...value];
    for (const f of fresh) {
      const existing = all.find((o) => same(o, f)) ?? f;
      if (!has(next, existing)) next.push(existing);
    }
    onChange(next);
    setSearch("");
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setSearch("");
      }}
      modal
    >
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-label={ariaLabel}
          className={cn(triggerClass, "flex-wrap py-1.5 pl-1.5")}
        >
          {value.length === 0 && <span className="flex-1 px-1.5 text-muted-foreground">{placeholder}</span>}
          {value.map((v) => (
            <span key={v} className="inline-flex max-w-full items-center gap-0.5 rounded bg-secondary px-1.5 py-0.5 text-xs">
              <span className="truncate">{v}</span>
              <span
                role="button"
                tabIndex={-1}
                aria-label={`Remove ${noun} ${v}`}
                className="text-muted-foreground hover:text-foreground"
                onPointerDown={(e) => e.preventDefault()}
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(v);
                }}
              >
                <X className="size-3" />
              </span>
            </span>
          ))}
          <ChevronsUpDown className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-(--radix-popover-trigger-width) min-w-60 p-0">
        <Command shouldFilter={false}>
          <CommandInput
            value={search}
            onValueChange={setSearch}
            placeholder={creatable ? `${searchPlaceholder} or add new` : searchPlaceholder}
            onKeyDown={(e) => {
              if (e.key === "Backspace" && !search && value.length) onChange(value.slice(0, -1));
            }}
          />
          <CommandList>
            {(!creatable || !typed) && shown.length === 0 && (
              <CommandEmpty>{creatable ? "Type to add." : "Nothing found."}</CommandEmpty>
            )}
            {shown.length > 0 && (
              <CommandGroup>
                {shown.map((o) => (
                  <CommandItem key={o} value={o} onSelect={() => toggle(o)}>
                    <span
                      className={cn(
                        "flex size-4 items-center justify-center rounded-[4px] border",
                        has(value, o) ? "border-primary bg-primary text-primary-foreground" : "border-input",
                      )}
                    >
                      {has(value, o) && <Check className="size-3 text-current" />}
                    </span>
                    <span className="truncate">{o}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {creatable && typed && !has(all, typed) && (
              <CommandGroup>
                <CommandItem value={`__create__${typed}`} onSelect={() => add(search)}>
                  <Plus /> Add “{typed}”
                </CommandItem>
              </CommandGroup>
            )}
            {footer && (
              <>
                <CommandSeparator />
                <div className="p-1">{footer}</div>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
