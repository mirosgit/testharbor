"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Bot, Check, ChevronDown, Link2, Plus, RefreshCw, Search, X } from "lucide-react";
import { memo, useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api, ApiError } from "@/lib/api";
import type { CatalogAction, CatalogItem, CatalogPreview } from "@/lib/types";
import { cn } from "@/lib/utils";

const fail = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong");

/** The project's catalog preview, or null when no agent has sent one. */
export function useCatalog(projectId: number) {
  return useQuery({
    queryKey: ["catalog", projectId],
    queryFn: () =>
      api.catalog(projectId).catch((e) => {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }),
    retry: false,
    refetchInterval: 30_000,
  });
}

const pending = (c: CatalogPreview) => c.counts.create + c.counts.update + c.counts.link + c.counts.outdated;

/** A strip under the suite picker: "Autotests: 12 to sync · Review", and the sync dialog. */
export function CatalogSyncStrip({ projectId, onApplied }: { projectId: number; onApplied: () => void }) {
  const { data: catalog } = useCatalog(projectId);
  const [open, setOpen] = useState(false);
  if (!catalog) return null;
  const n = pending(catalog);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "flex items-center gap-2 border-b px-3 py-2 text-left text-xs hover:bg-muted",
          n ? "text-foreground" : "text-muted-foreground",
        )}
        data-testid="catalog-strip"
      >
        <Bot className="size-3.5 shrink-0" />
        <span className="min-w-0 flex-1 truncate">
          {n ? (
            <>
              Autotests: <b>{n}</b> to sync
            </>
          ) : (
            "Autotests in sync"
          )}
        </span>
        <span className="text-primary">Review</span>
      </button>
      <CatalogSyncDialog open={open} onOpenChange={setOpen} projectId={projectId} onApplied={onApplied} />
    </>
  );
}

/** What happens to a test: a new one is created, linked or skipped; a linked or changed one applied or skipped. */
type Choice = { kind: "create" } | { kind: "link"; caseId: number; label: string } | { kind: "apply" } | { kind: "skip" };
type Tab = Exclude<CatalogAction, "unchanged">;

const CREATE: Choice = { kind: "create" };
const APPLY: Choice = { kind: "apply" };
const SKIP: Choice = { kind: "skip" };

const TABS: { id: Tab; label: string; hint: string }[] = [
  {
    id: "create",
    label: "New",
    hint: "Each new test becomes a case in Pending review, unless you link it to an existing case (similar ones are suggested) or skip it.",
  },
  { id: "link", label: "Link", hint: "Tagged with a case ID in the tests. Only the automation fields of these cases change." },
  { id: "update", label: "Changed", hint: "Their cases follow the tests and go back to Pending review." },
  { id: "outdated", label: "Removed", hint: "Their tests are gone. The cases are marked Outdated, never deleted." },
];

const CHANGE_LABEL: Record<string, string> = {
  title: "title",
  description: "description",
  preconditions: "preconditions",
  steps: "steps",
  expected_result: "expected result",
  roles: "roles",
  tags: "tags",
  automation_key: "automation key",
  automation_status: "automation status",
  state: "back to review",
};

const rowKey = (i: CatalogItem) => (i.action === "outdated" ? `outdated-${i.case_id}` : i.key);
const defaultChoice = (i: CatalogItem): Choice => (i.action === "create" ? CREATE : APPLY);

export function CatalogSyncDialog({
  open,
  onOpenChange,
  projectId,
  onApplied,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: number;
  onApplied: () => void;
}) {
  const qc = useQueryClient();
  const { data: catalog, refetch, isFetching } = useCatalog(projectId);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [tab, setTab] = useState<Tab | null>(null);
  const [query, setQuery] = useState("");
  const q = useDeferredValue(query.trim().toLowerCase());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setChoices({});
    setSelected(new Set());
    setTab(null);
    setQuery("");
    void refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const groups = useMemo(() => {
    const by: Record<CatalogAction, CatalogItem[]> = { create: [], link: [], update: [], outdated: [], unchanged: [] };
    for (const i of catalog?.items ?? []) by[i.action].push(i);
    return by;
  }, [catalog]);

  const current: Tab = tab ?? TABS.find((t) => groups[t.id].length)?.id ?? "create";

  // The rows of the tab that match the filter, by section path (in the catalog's order).
  const sections = useMemo(() => {
    const out = new Map<string, CatalogItem[]>();
    for (const i of groups[current]) {
      const path = i.path.join(" › ");
      const text = `${i.title} ${path} ${i.key} ${i.case_key ?? ""} ${i.case_title ?? ""}`.toLowerCase();
      if (q && !text.includes(q)) continue;
      const list = out.get(path) ?? [];
      list.push(i);
      out.set(path, list);
    }
    return [...out.entries()];
  }, [groups, current, q]);
  const shown = useMemo(() => sections.flatMap(([, items]) => items), [sections]);
  const picked = useMemo(() => shown.filter((i) => selected.has(i.key)), [shown, selected]);

  const plan = useMemo(() => {
    const links: Record<string, number> = {};
    const skip: string[] = [];
    let create = 0;
    let link = 0;
    let update = 0;
    for (const i of [...groups.create, ...groups.link, ...groups.update]) {
      const c = choices[i.key] ?? defaultChoice(i);
      if (c.kind === "skip") skip.push(i.key);
      else if (c.kind === "link") {
        links[i.key] = c.caseId;
        link++;
      } else if (i.action === "create") create++;
      else if (i.action === "link") link++;
      else update++;
    }
    const outdated = groups.outdated.length;
    return { links, skip, create, link, update, outdated, total: create + link + update + outdated };
  }, [groups, choices]);

  const choose = useCallback((key: string, c: Choice) => setChoices((s) => ({ ...s, [key]: c })), []);
  const select = useCallback(
    (keys: string[], on: boolean) =>
      setSelected((s) => {
        const n = new Set(s);
        for (const k of keys) {
          if (on) n.add(k);
          else n.delete(k);
        }
        return n;
      }),
    [],
  );

  // One choice for every selected row; "alike" links each new test to its most similar case.
  const bulk = (what: "create" | "alike" | "apply" | "skip") => {
    const next: Record<string, Choice> = {};
    for (const i of picked) {
      if (what === "alike") {
        const s = i.suggestions[0];
        if (s) next[i.key] = { kind: "link", caseId: s.case_id, label: `${s.key} ${s.title}` };
      } else next[i.key] = what === "create" ? CREATE : what === "apply" ? APPLY : SKIP;
    }
    const n = Object.keys(next).length;
    setChoices((s) => ({ ...s, ...next }));
    setSelected(new Set());
    const verb = {
      create: "will become new cases",
      alike: "linked to their most alike case",
      apply: "will be applied",
      skip: "skipped",
    }[what];
    toast.success(`${n} ${n === 1 ? "test" : "tests"} ${verb}`);
  };

  const apply = async () => {
    if (!catalog) return;
    const targets = Object.values(plan.links);
    if (new Set(targets).size !== targets.length) {
      toast.error("Two tests are linked to the same case. A case can be linked to one test.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.applyCatalog(projectId, { uploaded_at: catalog.uploaded_at, links: plan.links, skip: plan.skip });
      toast.success(
        [
          r.created && `${r.created} created`,
          r.linked && `${r.linked} linked`,
          r.updated && `${r.updated} updated`,
          r.outdated && `${r.outdated} outdated`,
        ]
          .filter(Boolean)
          .join(", ") || "Nothing to change",
      );
      qc.invalidateQueries({ queryKey: ["catalog", projectId] });
      onApplied();
      onOpenChange(false);
    } catch (e) {
      fail(e);
      if (e instanceof ApiError && e.status === 409) void refetch();
    } finally {
      setBusy(false);
    }
  };

  const tabInfo = TABS.find((t) => t.id === current)!;
  const selectable = current !== "outdated";
  const alike = picked.filter((i) => i.suggestions.length > 0).length;
  const inSync = !!catalog && pending(catalog) === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex h-[min(56rem,calc(100dvh-2rem))] flex-col gap-3 sm:max-w-5xl"
        data-testid="catalog-dialog"
      >
        <DialogHeader>
          <DialogTitle>Sync autotests</DialogTitle>
          <DialogDescription>
            {catalog
              ? `${catalog.items.length - catalog.counts.outdated} tests from ${catalog.agent ?? "an agent"}, ${new Date(
                  catalog.uploaded_at,
                ).toLocaleString()}. New cases go to the ${catalog.suite} suite.`
              : "Loading…"}
          </DialogDescription>
        </DialogHeader>

        {inSync ? (
          <p className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            All {groups.unchanged.length} tests are in sync with their cases.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <div role="tablist" className="flex flex-wrap gap-1 rounded-lg bg-muted p-1">
                {TABS.filter((t) => groups[t.id].length > 0).map((t) => (
                  <button
                    key={t.id}
                    role="tab"
                    type="button"
                    aria-selected={current === t.id}
                    onClick={() => {
                      setTab(t.id);
                      setSelected(new Set());
                    }}
                    className={cn(
                      "rounded-md px-3 py-1 text-sm transition-colors",
                      current === t.id ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {t.label} <span className="text-muted-foreground tabular-nums">{groups[t.id].length}</span>
                  </button>
                ))}
              </div>
              <div className="relative w-full sm:ml-auto sm:w-64">
                <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter tests…"
                  className="h-8 pl-8"
                  aria-label="Filter tests"
                />
              </div>
            </div>
            <p className="-mt-1 text-xs text-muted-foreground">{tabInfo.hint}</p>

            <div className="-mx-6 flex min-h-0 flex-1 flex-col overflow-y-auto border-y px-6" data-testid="catalog-list">
              {selectable && shown.length > 0 && (
                <label className="sticky top-0 z-10 flex items-center gap-3 border-b bg-background py-2 text-xs text-muted-foreground">
                  <Checkbox
                    checked={picked.length && picked.length === shown.length ? true : picked.length ? "indeterminate" : false}
                    onCheckedChange={(v) => select(shown.map((i) => i.key), v === true)}
                    aria-label="Select all shown tests"
                  />
                  {picked.length ? `${picked.length} of ${shown.length} selected` : `Select all ${shown.length}`}
                </label>
              )}
              {sections.map(([path, items]) => (
                <Section
                  key={path}
                  path={path}
                  items={items}
                  selectable={selectable}
                  selected={selected}
                  choices={choices}
                  onSelect={select}
                  onChoose={choose}
                  projectId={projectId}
                />
              ))}
              {shown.length === 0 && <p className="py-10 text-center text-sm text-muted-foreground">No tests match.</p>}

              {picked.length > 0 && (
                <div
                  className="sticky bottom-3 z-10 mx-auto mt-auto flex w-fit max-w-full flex-wrap items-center gap-1.5 rounded-lg border bg-popover p-1.5 pl-3 text-sm shadow-lg"
                  data-testid="catalog-bulk"
                >
                  <span className="mr-1 font-medium tabular-nums">{picked.length} selected</span>
                  {current === "create" ? (
                    <>
                      <Button size="sm" variant="outline" onClick={() => bulk("create")}>
                        <Plus /> New cases
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => bulk("alike")}
                        disabled={alike === 0}
                        title={alike ? undefined : "None of the selected tests has a similar case"}
                      >
                        <Link2 /> Link to most alike{alike > 0 && alike < picked.length && ` (${alike})`}
                      </Button>
                    </>
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => bulk("apply")}>
                      <Check /> Apply
                    </Button>
                  )}
                  <Button size="sm" variant="outline" onClick={() => bulk("skip")}>
                    <Ban /> Skip
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="size-8"
                    onClick={() => setSelected(new Set())}
                    aria-label="Clear selection"
                  >
                    <X />
                  </Button>
                </div>
              )}
            </div>
          </>
        )}

        <DialogFooter className="items-center gap-2 sm:justify-between">
          <p className="text-xs text-muted-foreground" data-testid="catalog-summary">
            {!inSync &&
              [
                plan.create && `create ${plan.create}`,
                plan.link && `link ${plan.link}`,
                plan.update && `update ${plan.update}`,
                plan.outdated && `outdate ${plan.outdated}`,
                plan.skip.length && `skip ${plan.skip.length}`,
              ]
                .filter(Boolean)
                .join(" · ")}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" size="icon" onClick={() => refetch()} disabled={isFetching} aria-label="Reload the catalog">
              <RefreshCw className={cn(isFetching && "animate-spin")} />
            </Button>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={apply} disabled={busy || !catalog || plan.total === 0}>
              {busy ? "Syncing…" : plan.total ? `Sync ${plan.total}` : "Sync"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const Section = memo(function Section({
  path,
  items,
  selectable,
  selected,
  choices,
  onSelect,
  onChoose,
  projectId,
}: {
  path: string;
  items: CatalogItem[];
  selectable: boolean;
  selected: Set<string>;
  choices: Record<string, Choice>;
  onSelect: (keys: string[], on: boolean) => void;
  onChoose: (key: string, c: Choice) => void;
  projectId: number;
}) {
  const n = items.filter((i) => selected.has(i.key)).length;
  return (
    <section className="min-w-0 border-b last:border-b-0">
      <div className="flex items-center gap-3 pt-3 pb-1 text-xs font-medium text-muted-foreground">
        {selectable && (
          <Checkbox
            checked={n && n === items.length ? true : n ? "indeterminate" : false}
            onCheckedChange={(v) => onSelect(items.map((i) => i.key), v === true)}
            aria-label={`Select all in ${path || "this section"}`}
          />
        )}
        <span className="min-w-0 truncate">{path || "No section"}</span>
        <span className="tabular-nums">{items.length}</span>
      </div>
      <ul className="grid">
        {items.map((i) => (
          <Row
            key={rowKey(i)}
            item={i}
            selectable={selectable}
            selected={selected.has(i.key)}
            choice={choices[i.key] ?? defaultChoice(i)}
            onSelect={onSelect}
            onChoose={onChoose}
            projectId={projectId}
          />
        ))}
      </ul>
    </section>
  );
});

const Row = memo(function Row({
  item,
  selectable,
  selected,
  choice,
  onSelect,
  onChoose,
  projectId,
}: {
  item: CatalogItem;
  selectable: boolean;
  selected: boolean;
  choice: Choice;
  onSelect: (keys: string[], on: boolean) => void;
  onChoose: (key: string, c: Choice) => void;
  projectId: number;
}) {
  const skipped = choice.kind === "skip";
  const best = item.suggestions[0];
  return (
    <li
      className={cn(
        "-mx-2 grid min-w-0 gap-2 rounded-md px-2 py-2 sm:grid-cols-[minmax(0,1fr)_16rem] sm:items-center",
        selected && "bg-primary/5",
      )}
      data-testid="catalog-item"
    >
      <div className="flex min-w-0 items-start gap-3">
        {selectable && (
          <Checkbox
            checked={selected}
            onCheckedChange={(v) => onSelect([item.key], v === true)}
            aria-label={`Select ${item.title}`}
            className="mt-0.5"
          />
        )}
        <div className={cn("grid min-w-0 gap-0.5", skipped && "opacity-50")}>
          <span className={cn("text-sm break-words", skipped && "line-through")}>{item.title}</span>
          {item.case_key && (
            <span className="truncate text-xs text-muted-foreground">
              <span className="font-mono">{item.case_key}</span>
              {item.case_title !== item.title && ` ${item.case_title}`}
            </span>
          )}
          {item.action === "update" && item.changes.length > 0 && (
            <span className="text-xs text-muted-foreground">
              Changes: {item.changes.map((c) => CHANGE_LABEL[c] ?? c).join(", ")}
            </span>
          )}
          {item.action === "create" && best && choice.kind === "create" && (
            <button
              type="button"
              className="flex min-w-0 items-center gap-1 text-left text-xs text-muted-foreground hover:text-foreground"
              onClick={() => onChoose(item.key, { kind: "link", caseId: best.case_id, label: `${best.key} ${best.title}` })}
              title="Link to this case instead of creating a new one"
            >
              <Link2 className="size-3 shrink-0" />
              <span className="truncate">
                Similar: <span className="font-mono">{best.key}</span> {best.title} · {Math.round(best.score * 100)}%
              </span>
            </button>
          )}
          {item.note && <span className="text-xs text-amber-700 dark:text-amber-400">{item.note}</span>}
        </div>
      </div>
      <div className={cn("min-w-0", selectable && "pl-7 sm:pl-0")}>
        {item.action === "create" ? (
          <DecisionPicker item={item} choice={choice} onChoose={onChoose} projectId={projectId} />
        ) : item.action === "outdated" ? (
          <span className="text-xs text-muted-foreground">Will be marked Outdated</span>
        ) : (
          <ApplyToggle on={!skipped} onChange={(on) => onChoose(item.key, on ? APPLY : SKIP)} label={item.title} />
        )}
      </div>
    </li>
  );
});

function ApplyToggle({ on, onChange, label }: { on: boolean; onChange: (on: boolean) => void; label: string }) {
  const options: [boolean, string][] = [
    [true, "Apply"],
    [false, "Skip"],
  ];
  return (
    <div className="inline-flex rounded-md border p-0.5 text-xs" role="radiogroup" aria-label={`Apply ${label}`}>
      {options.map(([value, text]) => (
        <button
          key={text}
          type="button"
          role="radio"
          aria-checked={on === value}
          onClick={() => onChange(value)}
          className={cn(
            "rounded px-2.5 py-1 transition-colors",
            on === value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

const choiceLabel = (c: Choice) =>
  c.kind === "create" ? "New case" : c.kind === "skip" ? "Skip for now" : c.kind === "link" ? `Link to ${c.label}` : "Apply";

/** What to do with a new test: a light button; the searchable menu mounts only when it is opened. */
function DecisionPicker({
  item,
  choice,
  onChoose,
  projectId,
}: {
  item: CatalogItem;
  choice: Choice;
  onChoose: (key: string, c: Choice) => void;
  projectId: number;
}) {
  const [open, setOpen] = useState(false);
  const Icon = choice.kind === "link" ? Link2 : choice.kind === "skip" ? Ban : Plus;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`What to do with ${item.title}`}
          className={cn(
            "flex h-8 w-full items-center gap-2 rounded-md border bg-background px-2.5 text-left text-sm shadow-xs outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50",
            choice.kind === "link" && "border-primary/40 bg-primary/5",
            choice.kind === "skip" && "text-muted-foreground",
          )}
        >
          <Icon className="size-3.5 shrink-0" />
          <span className="min-w-0 flex-1 truncate">{choiceLabel(choice)}</span>
          <ChevronDown className="size-3.5 shrink-0 opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        {open && (
          <CasePicker
            item={item}
            projectId={projectId}
            onPick={(c) => {
              onChoose(item.key, c);
              setOpen(false);
            }}
          />
        )}
      </PopoverContent>
    </Popover>
  );
}

function CasePicker({ item, projectId, onPick }: { item: CatalogItem; projectId: number; onPick: (c: Choice) => void }) {
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const { data, isFetching } = useQuery({
    queryKey: ["catalog-link-search", projectId, q],
    queryFn: () => api.cases(projectId, { q }, { limit: 20 }),
    enabled: q.length > 0,
    staleTime: 30_000,
  });
  const found = (data?.items ?? []).filter((c) => !c.catalog_managed && !item.suggestions.some((s) => s.case_id === c.id));
  return (
    <Command shouldFilter={false}>
      <CommandInput value={search} onValueChange={setSearch} placeholder="Find a case by title or C123…" />
      <CommandList>
        {!q && (
          <CommandGroup>
            <CommandItem onSelect={() => onPick(CREATE)}>
              <Plus /> Create a new case
            </CommandItem>
            <CommandItem onSelect={() => onPick(SKIP)}>
              <Ban /> Skip for now
            </CommandItem>
          </CommandGroup>
        )}
        {!q && item.suggestions.length > 0 && (
          <CommandGroup heading="Similar cases">
            {item.suggestions.map((s) => (
              <CommandItem
                key={s.case_id}
                onSelect={() => onPick({ kind: "link", caseId: s.case_id, label: `${s.key} ${s.title}` })}
              >
                <Link2 />
                <span className="font-mono text-xs">{s.key}</span>
                <span className="min-w-0 flex-1 truncate">{s.title}</span>
                <span className="text-xs text-muted-foreground tabular-nums">{Math.round(s.score * 100)}%</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {q && found.length > 0 && (
          <CommandGroup heading="Cases">
            {found.map((c) => (
              <CommandItem key={c.id} onSelect={() => onPick({ kind: "link", caseId: c.id, label: `${c.key} ${c.title}` })}>
                <Link2 />
                <span className="font-mono text-xs">{c.key}</span>
                <span className="min-w-0 flex-1 truncate">{c.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {q && (isFetching || data === undefined ? (
          <p className="px-3 py-6 text-center text-sm text-muted-foreground">Searching…</p>
        ) : (
          found.length === 0 && <CommandEmpty>No manual case matches.</CommandEmpty>
        ))}
        {!q && <p className="border-t px-3 py-2 text-xs text-muted-foreground">Type to link it to any other manual case.</p>}
      </CommandList>
    </Command>
  );
}
