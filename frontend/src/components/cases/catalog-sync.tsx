"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Link2, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import type { CatalogItem, CatalogPreview } from "@/lib/types";
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

type Choice = "create" | "skip" | "other" | `link:${number}`;

const CHANGE_LABEL: Record<string, string> = {
  title: "title",
  description: "description",
  preconditions: "preconditions",
  steps: "steps",
  roles: "roles",
  tags: "tags",
  automation_key: "automation key",
  automation_status: "automation status",
  state: "state",
};

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
  const [choice, setChoice] = useState<Record<string, Choice>>({});
  const [other, setOther] = useState<Record<string, string>>({});
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setChoice({});
    setOther({});
    setSkipped(new Set());
    void refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const groups = useMemo(() => {
    const by: Record<string, CatalogItem[]> = { create: [], link: [], update: [], outdated: [], unchanged: [] };
    for (const i of catalog?.items ?? []) by[i.action].push(i);
    return by;
  }, [catalog]);

  const decide = (key: string): Choice => choice[key] ?? "create";
  const otherId = (key: string) => {
    const m = /^\s*[Cc]?(\d+)\s*$/.exec(other[key] ?? "");
    return m ? Number(m[1]) : null;
  };

  const plan = useMemo(() => {
    const links: Record<string, number> = {};
    const skip = new Set(skipped);
    let invalid = 0;
    for (const i of groups.create) {
      const c = decide(i.key);
      if (c === "skip") skip.add(i.key);
      else if (c === "other") {
        const id = otherId(i.key);
        if (id) links[i.key] = id;
        else invalid++;
      } else if (c.startsWith("link:")) links[i.key] = Number(c.slice(5));
    }
    const create = groups.create.filter((i) => decide(i.key) === "create").length;
    const linkCount =
      Object.keys(links).length + groups.link.filter((i) => !skip.has(i.key)).length;
    const update = groups.update.filter((i) => !skip.has(i.key)).length;
    return { links, skip: [...skip], invalid, create, link: linkCount, update, outdated: groups.outdated.length };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groups, choice, other, skipped]);

  const apply = async () => {
    if (!catalog) return;
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

  const toggle = (key: string, on: boolean) =>
    setSkipped((s) => {
      const n = new Set(s);
      if (on) n.delete(key);
      else n.add(key);
      return n;
    });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] flex-col sm:max-w-3xl" data-testid="catalog-dialog">
        <DialogHeader>
          <DialogTitle>Sync autotests</DialogTitle>
          <DialogDescription>
            {catalog ? (
              <>
                {catalog.items.length - catalog.counts.outdated} tests from {catalog.agent ?? "an agent"},{" "}
                {new Date(catalog.uploaded_at).toLocaleString()}. New tests become cases in the{" "}
                <b>{catalog.suite}</b> suite, unless you link them to an existing case.
              </>
            ) : (
              "Loading…"
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="-mx-6 grid min-h-0 flex-1 gap-5 overflow-y-auto px-6">
          {groups.create.length > 0 && (
            <Group title="New tests" count={groups.create.length} hint="A similar existing case? Link the test to it instead of creating a duplicate.">
              {groups.create.map((i) => {
                const c = decide(i.key);
                return (
                  <Row key={i.key} item={i}>
                    <div className="grid w-full gap-1 sm:w-72">
                      <Select value={c} onValueChange={(v) => setChoice((s) => ({ ...s, [i.key]: v as Choice }))}>
                        <SelectTrigger size="sm" className="w-full" aria-label={`What to do with ${i.title}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="create">Create a new case</SelectItem>
                          {i.suggestions.map((s) => (
                            <SelectItem key={s.case_id} value={`link:${s.case_id}`}>
                              Link to {s.key} · {Math.round(s.score * 100)}% alike
                            </SelectItem>
                          ))}
                          <SelectItem value="other">Link to another case…</SelectItem>
                          <SelectItem value="skip">Skip for now</SelectItem>
                        </SelectContent>
                      </Select>
                      {c === "other" && (
                        <Input
                          className="h-8"
                          placeholder="Case ID, e.g. C142"
                          value={other[i.key] ?? ""}
                          aria-invalid={!otherId(i.key)}
                          onChange={(e) => setOther((s) => ({ ...s, [i.key]: e.target.value }))}
                        />
                      )}
                    </div>
                    {i.suggestions.length > 0 && (
                      <ul className="col-span-full grid gap-0.5 text-xs text-muted-foreground">
                        {i.suggestions.map((s) => (
                          <li key={s.case_id} className="flex min-w-0 gap-1">
                            <Link2 className="mt-0.5 size-3 shrink-0" />
                            <span className="truncate">
                              Similar: <span className="font-mono">{s.key}</span> {s.title}
                              {s.path && <span className="opacity-70"> · {s.path}</span>}
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Row>
                );
              })}
            </Group>
          )}
          {groups.link.length > 0 && (
            <Group title="Link to existing cases" count={groups.link.length} hint="Tagged with a case ID in the tests. Only the automation fields of these cases change.">
              {groups.link.map((i) => (
                <Row key={i.key} item={i} target={i}>
                  <Include on={!skipped.has(i.key)} onChange={(on) => toggle(i.key, on)} />
                </Row>
              ))}
            </Group>
          )}
          {groups.update.length > 0 && (
            <Group title="Changed tests" count={groups.update.length} hint="Their cases follow the tests.">
              {groups.update.map((i) => (
                <Row key={i.key} item={i} target={i} changes>
                  <Include on={!skipped.has(i.key)} onChange={(on) => toggle(i.key, on)} />
                </Row>
              ))}
            </Group>
          )}
          {groups.outdated.length > 0 && (
            <Group title="Removed tests" count={groups.outdated.length} hint="Their cases are marked Outdated, not deleted.">
              {groups.outdated.map((i) => (
                <Row key={`outdated-${i.case_id}`} item={i} target={i} />
              ))}
            </Group>
          )}
          {catalog && pending(catalog) === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              All {groups.unchanged.length} tests are in sync with their cases.
            </p>
          )}
        </div>

        <DialogFooter className="items-center gap-2 sm:justify-between">
          <p className="text-xs text-muted-foreground" data-testid="catalog-summary">
            {catalog && pending(catalog) > 0 &&
              [
                plan.create && `create ${plan.create}`,
                plan.link && `link ${plan.link}`,
                plan.update && `update ${plan.update}`,
                plan.outdated && `outdate ${plan.outdated}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            {groups.unchanged.length > 0 && pending(catalog!) > 0 && ` · ${groups.unchanged.length} unchanged`}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => refetch()} disabled={isFetching} aria-label="Reload the catalog">
              <RefreshCw className={cn(isFetching && "animate-spin")} />
            </Button>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={apply} disabled={busy || !catalog || pending(catalog) === 0 || plan.invalid > 0}>
              {busy ? "Syncing…" : "Sync"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Group({ title, count, hint, children }: { title: string; count: number; hint: string; children: React.ReactNode }) {
  return (
    <section className="grid min-w-0 gap-2">
      <div>
        <h3 className="text-sm font-medium">
          {title} <span className="text-muted-foreground">{count}</span>
        </h3>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
      <ul className="grid divide-y rounded-md border">{children}</ul>
    </section>
  );
}

function Row({
  item,
  target,
  changes,
  children,
}: {
  item: CatalogItem;
  target?: CatalogItem;
  changes?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <li className="grid min-w-0 gap-2 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start" data-testid="catalog-item">
      <div className="grid min-w-0 gap-0.5">
        <span className="text-sm break-words">{item.title}</span>
        <span className="truncate text-xs text-muted-foreground">
          {target?.case_key ? (
            <>
              <span className="font-mono">{target.case_key}</span>
              {target.case_title !== item.title && ` ${target.case_title}`}
            </>
          ) : (
            item.path.join(" › ")
          )}
          {changes && item.changes.length > 0 && ` · ${item.changes.map((c) => CHANGE_LABEL[c] ?? c).join(", ")}`}
        </span>
        {item.note && <span className="text-xs text-amber-700 dark:text-amber-400">{item.note}</span>}
      </div>
      {children}
    </li>
  );
}

function Include({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
      <Checkbox checked={on} onCheckedChange={(v) => onChange(v === true)} />
      Apply
    </label>
  );
}
