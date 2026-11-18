"use client";

import { ArrowDownNarrowWide, ArrowUpNarrowWide, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export interface SortOption<K extends string> {
  key: K;
  label: string;
  /** Direction used when the option is picked (e.g. newest first for dates). */
  defaultOrder?: "asc" | "desc";
  /** Has no direction (e.g. manual order). */
  fixed?: boolean;
}

export interface SortState<K extends string> {
  sort: K;
  order: "asc" | "desc";
}

export function SortMenu<K extends string>({
  options,
  value,
  onChange,
  hint,
}: {
  options: SortOption<K>[];
  value: SortState<K>;
  onChange: (v: SortState<K>) => void;
  hint?: string;
}) {
  const current = options.find((o) => o.key === value.sort) ?? options[0];
  const Icon = value.order === "desc" ? ArrowDownNarrowWide : ArrowUpNarrowWide;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5" aria-label={`Sort: ${current.label}`}>
          <Icon className="text-muted-foreground" />
          <span className="text-muted-foreground">Sort:</span> {current.label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        {hint && <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{hint}</DropdownMenuLabel>}
        {options.map((o) => (
          <DropdownMenuItem
            key={o.key}
            onSelect={() => onChange({ sort: o.key, order: o.key === value.sort ? value.order : (o.defaultOrder ?? "asc") })}
          >
            <Check className={cn(o.key === value.sort ? "opacity-100" : "opacity-0")} />
            {o.label}
          </DropdownMenuItem>
        ))}
        {!current.fixed && (
          <>
            <DropdownMenuSeparator />
            {(["asc", "desc"] as const).map((dir) => (
              <DropdownMenuItem key={dir} onSelect={() => onChange({ ...value, order: dir })}>
                <Check className={cn(value.order === dir ? "opacity-100" : "opacity-0")} />
                {dir === "asc" ? "Ascending" : "Descending"}
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** "‹ 1–100 of 340 ›" with a page size picker. */
export function Pager({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
  sizes = [50, 100, 200, 500],
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (p: number) => void;
  onPageSize?: (n: number) => void;
  sizes?: number[];
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= Math.min(pageSize, ...sizes)) return null;
  return (
    <div className="flex flex-wrap items-center justify-end gap-2 text-sm" data-testid="pager">
      {onPageSize && (
        <label className="mr-2 flex items-center gap-1.5 text-muted-foreground">
          Per page
          <select
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
            className="h-8 rounded-md border bg-transparent px-1.5 text-foreground"
            aria-label="Per page"
          >
            {sizes.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      )}
      <span className="text-muted-foreground tabular-nums">
        {page * pageSize + 1}–{Math.min((page + 1) * pageSize, total)} of {total}
      </span>
      <Button size="sm" variant="outline" disabled={page === 0} onClick={() => onPage(page - 1)} aria-label="Previous page">
        Previous
      </Button>
      <span className="text-muted-foreground tabular-nums">
        {page + 1} / {pages}
      </span>
      <Button
        size="sm"
        variant="outline"
        disabled={page + 1 >= pages}
        onClick={() => onPage(page + 1)}
        aria-label="Next page"
      >
        Next
      </Button>
    </div>
  );
}
