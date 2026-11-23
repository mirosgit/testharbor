"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Search } from "lucide-react";
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
import { buildTree, flatten, type SectionNode } from "@/lib/tree";
import type { TestCase } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Expanded by default up to this many cases in the suite; larger suites open collapsed (search still finds all). */
const EXPAND_UP_TO = 200;

/** Add cases to an existing run: pick single cases or whole sections; cases already in the run are shown, not pickable. */
export function AddCasesDialog({
  open,
  onOpenChange,
  projectId,
  runId,
  inRun,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: number;
  runId: number;
  inRun: Set<number>;
  onAdded: () => void;
}) {
  const [suiteId, setSuiteId] = useState<number | undefined>();
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [toggled, setToggled] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setPicked(new Set());
    setToggled(new Set());
  }, [open]);

  const { data: suites = [] } = useQuery({
    queryKey: ["suites", projectId],
    queryFn: () => api.suites(projectId),
    enabled: open,
  });
  const suite = suiteId ?? suites[0]?.id;
  const { data: sections = [] } = useQuery({
    queryKey: ["sections", suite],
    queryFn: () => api.sections(suite!),
    enabled: open && !!suite,
  });
  const { data: caseList, isLoading } = useQuery({
    queryKey: ["add-cases", projectId, suite],
    queryFn: () => api.cases(projectId, { suite_id: suite }),
    enabled: open && !!suite,
  });

  const flat = useMemo(() => flatten(buildTree(sections)), [sections]);
  const all = useMemo(() => caseList?.items ?? [], [caseList]);
  const shown = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return all;
    return all.filter((c) => words.every((w) => `${c.key} ${c.title} ${c.tags.join(" ")}`.toLowerCase().includes(w)));
  }, [all, q]);
  const bySection = useMemo(() => {
    const m = new Map<number, TestCase[]>();
    for (const c of shown) m.set(c.section_id, [...(m.get(c.section_id) ?? []), c]);
    return m;
  }, [shown]);
  // Each section's shown cases, its subsections' included.
  const deep = useMemo(() => {
    const out = new Map<number, TestCase[]>();
    const walk = (n: SectionNode): TestCase[] => {
      const list = [...(bySection.get(n.id) ?? []), ...n.children.flatMap(walk)];
      out.set(n.id, list);
      return list;
    };
    buildTree(sections).forEach(walk);
    return out;
  }, [sections, bySection]);

  const expandedByDefault = all.length <= EXPAND_UP_TO;
  // Searching opens everything that matches; otherwise `toggled` flips a section from its default.
  const isOpen = (id: number) => q !== "" || expandedByDefault !== toggled.has(id);
  const hiddenByParent = (s: SectionNode): boolean => {
    let p = s.parent_id != null ? flat.find((x) => x.id === s.parent_id) : undefined;
    while (p) {
      if (!isOpen(p.id)) return true;
      p = p.parent_id != null ? flat.find((x) => x.id === p!.parent_id) : undefined;
    }
    return false;
  };

  const set = (cases: TestCase[], on: boolean) =>
    setPicked((prev) => {
      const n = new Set(prev);
      for (const c of cases) if (!inRun.has(c.id)) (on ? n.add(c.id) : n.delete(c.id));
      return n;
    });

  const submit = async () => {
    setBusy(true);
    try {
      await api.addRunCases(runId, { case_ids: [...picked] });
      toast.success(`Added ${picked.size} ${picked.size === 1 ? "case" : "cases"} to the run`);
      onAdded();
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not add the cases");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl" data-testid="add-cases-dialog">
        <DialogHeader>
          <DialogTitle>Add cases to the run</DialogTitle>
          <DialogDescription>Cases already in the run are marked and can&apos;t be picked again.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,12rem)_minmax(0,1fr)]">
          {suites.length > 1 && (
            <Select
              value={suite ? String(suite) : undefined}
              onValueChange={(v) => {
                setSuiteId(Number(v));
                setToggled(new Set());
              }}
            >
              <SelectTrigger className="h-8 w-full" aria-label="Suite">
                <SelectValue placeholder="Suite" />
              </SelectTrigger>
              <SelectContent>
                {suites.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>
                    {s.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <div className={cn("relative", suites.length <= 1 && "sm:col-span-2")}>
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="h-8 pl-8"
              placeholder="Search by title, C123 or tag"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              autoFocus
            />
          </div>
        </div>
        <div className="max-h-[55vh] min-h-40 overflow-y-auto rounded-md border px-2 py-1">
          {isLoading ? (
            <p className="py-4 text-center text-sm text-muted-foreground">Loading the cases…</p>
          ) : !shown.length ? (
            <p className="py-4 text-center text-sm text-muted-foreground">{q ? "No cases match." : "This suite has no cases."}</p>
          ) : (
            <ul>
              {flat.map((s) => {
                const cases = deep.get(s.id) ?? [];
                if (!cases.length || hiddenByParent(s)) return null;
                const addable = cases.filter((c) => !inRun.has(c.id));
                const n = addable.filter((c) => picked.has(c.id)).length;
                const own = bySection.get(s.id) ?? [];
                return (
                  <li key={s.id}>
                    <div className="flex items-center gap-1.5 py-1" style={{ paddingLeft: s.depth * 16 }}>
                      <button
                        type="button"
                        className="text-muted-foreground"
                        aria-label={isOpen(s.id) ? `Collapse ${s.name}` : `Expand ${s.name}`}
                        onClick={() =>
                          setToggled((t) => {
                            const next = new Set(t);
                            if (next.has(s.id)) next.delete(s.id);
                            else next.add(s.id);
                            return next;
                          })
                        }
                      >
                        <ChevronRight className={cn("size-3.5 transition-transform", isOpen(s.id) && "rotate-90")} />
                      </button>
                      <Checkbox
                        aria-label={`All cases in ${s.name}`}
                        disabled={!addable.length}
                        checked={addable.length > 0 && n === addable.length ? true : n ? "indeterminate" : false}
                        onCheckedChange={(v) => set(cases, v === true)}
                      />
                      <span className="min-w-0 truncate text-sm font-medium">{s.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {n ? `${n}/` : ""}
                        {addable.length}
                        {addable.length < cases.length && ` · ${cases.length - addable.length} in run`}
                      </span>
                    </div>
                    {isOpen(s.id) && own.length > 0 && (
                      <ul>
                        {own.map((c) => {
                          const already = inRun.has(c.id);
                          return (
                            <li key={c.id}>
                              <label
                                className={cn(
                                  "flex items-start gap-2 py-1 text-sm",
                                  already ? "cursor-default text-muted-foreground" : "cursor-pointer",
                                )}
                                style={{ paddingLeft: (s.depth + 1) * 16 + 20 }}
                              >
                                <Checkbox
                                  className="mt-0.5"
                                  disabled={already}
                                  checked={already || picked.has(c.id)}
                                  onCheckedChange={(v) => set([c], v === true)}
                                />
                                <span className="min-w-0 flex-1 break-words">{c.title}</span>
                                {already && <span className="shrink-0 text-xs">In run</span>}
                                <span className="shrink-0 font-mono text-xs text-muted-foreground">{c.key}</span>
                              </label>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <DialogFooter className="items-center gap-2 sm:justify-between">
          {picked.size > 0 ? (
            <button type="button" className="text-xs text-muted-foreground hover:underline" onClick={() => setPicked(new Set())}>
              Clear the selection
            </button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={busy || picked.size === 0} data-testid="add-cases-submit">
              {busy ? "Adding…" : picked.size ? `Add ${picked.size} ${picked.size === 1 ? "case" : "cases"}` : "Add cases"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
