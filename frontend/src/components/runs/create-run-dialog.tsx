"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PlayCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { isFiltered, toCaseFilter, type Filters } from "@/components/cases/filter-bar";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { buildTree, flatten } from "@/lib/tree";
import type { RunSelection } from "@/lib/types";
import { cn } from "@/lib/utils";

type Mode = "suite" | "sections" | "view" | "selected";

export interface RunContext {
  suiteId?: number;
  sectionId?: number | null;
  filters?: Filters;
  selectedIds?: number[];
  /** Number of cases in the current view (for the "current view" option). */
  visibleCount?: number;
}

export function CreateRunButton({ projectId, ...ctx }: RunContext & { projectId: number }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <PlayCircle /> Create run
      </Button>
      <CreateRunDialog open={open} onOpenChange={setOpen} projectId={projectId} context={ctx} />
    </>
  );
}

export function CreateRunDialog({
  open,
  onOpenChange,
  projectId,
  context = {},
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: number;
  context?: RunContext;
}) {
  const router = useRouter();
  const qc = useQueryClient();
  const hasSelected = (context.selectedIds?.length ?? 0) > 0;
  const f = context.filters;
  const hasView =
    context.visibleCount !== undefined &&
    (context.sectionId != null || (!!f && isFiltered(f)));

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState<Mode>("suite");
  const [suiteId, setSuiteId] = useState<number | undefined>(context.suiteId);
  const [sectionIds, setSectionIds] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(`Test run ${new Date().toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`);
    setDescription("");
    setMode(hasSelected ? "selected" : hasView ? "view" : "suite");
    setSuiteId(context.suiteId);
    setSectionIds(new Set());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const { data: suites = [] } = useQuery({
    queryKey: ["suites", projectId],
    queryFn: () => api.suites(projectId),
    enabled: open,
  });
  const effectiveSuite = suiteId ?? suites[0]?.id;
  const { data: sections = [] } = useQuery({
    queryKey: ["sections", effectiveSuite],
    queryFn: () => api.sections(effectiveSuite!),
    enabled: open && !!effectiveSuite,
  });
  const flat = useMemo(() => flatten(buildTree(sections)), [sections]);

  const toggleSection = (id: number) =>
    setSectionIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const selection = (): RunSelection => {
    switch (mode) {
      case "selected":
        return { case_ids: context.selectedIds };
      case "view":
        return {
          filter: {
            suite_id: context.suiteId,
            section_id: context.sectionId ?? undefined,
            ...(f ? toCaseFilter(f) : {}),
          },
        };
      case "sections":
        return { section_ids: [...sectionIds] };
      default:
        return { suite_id: effectiveSuite };
    }
  };

  const suiteCount = suites.find((s) => s.id === effectiveSuite)?.case_count ?? 0;
  const options: { value: Mode; label: string; hint?: string; show: boolean }[] = [
    { value: "selected", label: "Selected cases", hint: `${context.selectedIds?.length} cases`, show: hasSelected },
    { value: "view", label: "Cases in the current view", hint: `${context.visibleCount} cases (section and filters)`, show: hasView },
    { value: "suite", label: "Whole suite", hint: `${suiteCount} cases`, show: true },
    { value: "sections", label: "Pick sections", hint: "Subsections are included", show: true },
  ];

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mode === "sections" && sectionIds.size === 0) {
      toast.error("Pick at least one section");
      return;
    }
    setBusy(true);
    try {
      const run = await api.createRun(projectId, { name: name.trim(), description, ...selection() });
      qc.invalidateQueries({ queryKey: ["runs", projectId] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success(`Run created with ${run.stats.total} cases`);
      onOpenChange(false);
      router.push(`/projects/${projectId}/runs/${run.id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create run");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>New test run</DialogTitle>
            <DialogDescription>Choose which cases to include. You can add more cases later.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="run-name">Name</Label>
            <Input id="run-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="run-desc">Description</Label>
            <Textarea id="run-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
          </div>
          <fieldset className="grid gap-2">
            <legend className="mb-2 text-sm font-medium">Cases</legend>
            {options
              .filter((o) => o.show)
              .map((o) => (
                <label
                  key={o.value}
                  className={cn(
                    "flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 text-sm",
                    mode === o.value && "border-primary bg-primary/5",
                  )}
                >
                  <input
                    type="radio"
                    name="run-mode"
                    value={o.value}
                    checked={mode === o.value}
                    onChange={() => setMode(o.value)}
                    className="accent-primary"
                  />
                  <span className="flex-1">{o.label}</span>
                  {o.hint && <span className="text-xs text-muted-foreground">{o.hint}</span>}
                </label>
              ))}
          </fieldset>
          {(mode === "suite" || mode === "sections") && (
            <div className="grid gap-2">
              <Select value={effectiveSuite ? String(effectiveSuite) : undefined} onValueChange={(v) => { setSuiteId(Number(v)); setSectionIds(new Set()); }}>
                <SelectTrigger className="w-full" aria-label="Suite">
                  <SelectValue placeholder="Choose a suite" />
                </SelectTrigger>
                <SelectContent>
                  {suites.map((s) => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      {s.name} ({s.case_count})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {mode === "sections" && (
                <div className="max-h-56 overflow-y-auto rounded-md border p-1">
                  {flat.length === 0 && <p className="p-2 text-sm text-muted-foreground">No sections.</p>}
                  {flat.map((s) => (
                    <label
                      key={s.id}
                      className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted"
                      style={{ paddingLeft: 8 + s.depth * 16 }}
                    >
                      <Checkbox checked={sectionIds.has(s.id)} onCheckedChange={() => toggleSection(s.id)} />
                      <span className="flex-1">{s.name}</span>
                      <span className="text-xs text-muted-foreground">{s.totalCases}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || !name.trim()}>
              {busy ? "Creating…" : "Create run"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
