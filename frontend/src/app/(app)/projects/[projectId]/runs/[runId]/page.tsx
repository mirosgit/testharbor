"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Lock, LockOpen, MoreHorizontal, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { toast } from "sonner";

import { AutomationIcon, PriorityBadge, StatusBadge } from "@/components/badges";
import { ConfirmDialog, NameDialog } from "@/components/dialogs";
import { Markdown } from "@/components/markdown";
import { ExecuteSheet } from "@/components/runs/execute-sheet";
import { passRate, percentDone, RunProgress, StatusCounts } from "@/components/runs/progress";
import { CiMeta, RunSourceBadge, timeAgo } from "@/components/runs/run-meta";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { statusBg, statusLabel } from "@/lib/labels";
import type { ResultStatus, RunCase } from "@/lib/types";
import { cn } from "@/lib/utils";

const SETTABLE: ResultStatus[] = ["passed", "failed", "blocked", "retest", "skipped"];

export default function RunPage() {
  return (
    <Suspense>
      <RunView />
    </Suspense>
  );
}

function RunView() {
  const { projectId: pid, runId: rid } = useParams<{ projectId: string; runId: string }>();
  const projectId = Number(pid);
  const runId = Number(rid);
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const qc = useQueryClient();

  const runQ = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });
  const casesQ = useQuery({ queryKey: ["run-cases", runId], queryFn: () => api.runCases(runId) });
  const run = runQ.data;
  const readOnly = !!run?.closed;

  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [dialog, setDialog] = useState<"edit" | "delete" | null>(null);

  const openCaseId = search.get("case") ? Number(search.get("case")) : null;
  const setOpenCase = (id: number | null) => {
    const next = new URLSearchParams(search.toString());
    if (id === null) next.delete("case");
    else next.set("case", String(id));
    router.replace(`${pathname}?${next}`, { scroll: false });
  };

  const all = casesQ.data ?? [];
  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return all.filter(
      (c) =>
        (statusFilter.size === 0 || statusFilter.has(c.status)) &&
        (!needle || c.title.toLowerCase().includes(needle) || c.key.toLowerCase() === needle),
    );
  }, [all, statusFilter, q]);
  const groups = useMemo(() => {
    const m = new Map<string, RunCase[]>();
    for (const c of visible) {
      const k = c.section_path.replaceAll(" > ", " › ") || "—";
      if (!m.has(k)) m.set(k, []);
      m.get(k)!.push(c);
    }
    return [...m.entries()];
  }, [visible]);
  const openCase = all.find((c) => c.case_id === openCaseId) ?? null;

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["run", runId] });
    qc.invalidateQueries({ queryKey: ["run-cases", runId] });
    qc.invalidateQueries({ queryKey: ["runs", projectId] });
    qc.invalidateQueries({ queryKey: ["case-history"] });
    qc.invalidateQueries({ queryKey: ["run-results", runId] });
  };
  const fail = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong");

  const setStatuses = useMutation({
    mutationFn: ({ ids, status }: { ids: number[]; status: ResultStatus }) =>
      api.addResults(runId, ids.map((case_id) => ({ case_id, status }))),
    onSuccess: (_, { ids, status }) => {
      toast.success(`${ids.length === 1 ? all.find((c) => c.case_id === ids[0])?.key : `${ids.length} cases`}: ${statusLabel[status]}`);
      setSelected(new Set());
      invalidate();
    },
    onError: fail,
  });

  const toggleClosed = useMutation({
    mutationFn: () => api.updateRun(runId, { closed: !run!.closed }),
    onSuccess: (r) => {
      toast.success(r.closed ? "Run closed" : "Run reopened");
      invalidate();
    },
    onError: fail,
  });

  const nextUntested = () => {
    const idx = all.findIndex((c) => c.case_id === openCaseId);
    const after = [...all.slice(idx + 1), ...all.slice(0, idx)];
    const next = after.find((c) => c.status === "untested" && c.case_id !== openCaseId);
    if (next) setOpenCase(next.case_id);
    else {
      toast.success("No untested cases left 🎉");
      setOpenCase(null);
    }
  };

  if (runQ.isError) {
    return <p className="p-8 text-muted-foreground">Run not found.</p>;
  }

  return (
    <main className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-6">
        <Link
          href={`/projects/${projectId}/runs`}
          className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> All runs
        </Link>

        {!run ? (
          <Skeleton className="h-32" />
        ) : (
          <div className="mb-6 grid gap-4">
            <div className="flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <RunSourceBadge run={run} />
                  <span className="text-sm text-muted-foreground">R{run.id}</span>
                  {run.closed && (
                    <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                      <Lock className="size-3" /> Closed
                    </span>
                  )}
                </div>
                <h1 className="mt-1 text-2xl font-semibold">{run.name}</h1>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                  <span>Created {timeAgo(run.created_at)}</span>
                  <CiMeta run={run} />
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={() => toggleClosed.mutate()}>
                {run.closed ? (
                  <>
                    <LockOpen /> Reopen
                  </>
                ) : (
                  <>
                    <Lock /> Close run
                  </>
                )}
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon-sm" aria-label="Run actions">
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => setDialog("edit")}>Edit</DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onSelect={() => setDialog("delete")}>
                    <Trash2 /> Delete run
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            {run.description && <Markdown className="text-muted-foreground">{run.description}</Markdown>}

            <div className="grid gap-3 rounded-lg border p-4">
              <div className="flex items-end gap-6">
                <div>
                  <div className="text-3xl font-semibold tabular-nums">{passRate(run.stats)}%</div>
                  <div className="text-xs text-muted-foreground">passed of executed</div>
                </div>
                <div>
                  <div className="text-3xl font-semibold tabular-nums">{percentDone(run.stats)}%</div>
                  <div className="text-xs text-muted-foreground">
                    executed ({run.stats.total - run.stats.untested}/{run.stats.total})
                  </div>
                </div>
              </div>
              <RunProgress stats={run.stats} className="h-3" />
              <StatusCounts
                stats={run.stats}
                active={statusFilter}
                onToggle={(s) =>
                  setStatusFilter((prev) => {
                    const n = new Set(prev);
                    if (n.has(s)) n.delete(s);
                    else n.add(s);
                    return n;
                  })
                }
              />
            </div>
          </div>
        )}

        <div className="mb-3 flex items-center gap-2">
          <div className="relative w-64">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search cases…"
              className="h-8 pl-8"
              aria-label="Search run cases"
            />
          </div>
          {statusFilter.size > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setStatusFilter(new Set())}>
              Clear status filter
            </Button>
          )}
          {selected.size > 0 && !readOnly && (
            <div className="ml-auto flex items-center gap-2 text-sm">
              <span className="font-medium">{selected.size} selected</span>
              <StatusMenu label="Set status" onPick={(status) => setStatuses.mutate({ ids: [...selected], status })} />
              <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                Clear
              </Button>
            </div>
          )}
        </div>

        {casesQ.isLoading ? (
          <div className="grid gap-2">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        ) : all.length === 0 ? (
          <p className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
            This run has no cases.
          </p>
        ) : groups.length === 0 ? (
          <p className="p-12 text-center text-muted-foreground">No cases match.</p>
        ) : (
          <div className="grid gap-5" data-testid="run-cases">
            {groups.map(([path, cases]) => (
              <section key={path} aria-label={path}>
                <div className="mb-1.5 flex items-center gap-2 px-2">
                  {!readOnly && (
                    <Checkbox
                      checked={
                        cases.every((c) => selected.has(c.case_id))
                          ? true
                          : cases.some((c) => selected.has(c.case_id))
                            ? "indeterminate"
                            : false
                      }
                      onCheckedChange={(v) =>
                        setSelected((prev) => {
                          const n = new Set(prev);
                          cases.forEach((c) => (v === true ? n.add(c.case_id) : n.delete(c.case_id)));
                          return n;
                        })
                      }
                      aria-label={`Select all in ${path}`}
                    />
                  )}
                  <h3 className="text-sm font-semibold">{path}</h3>
                  <span className="text-xs text-muted-foreground">{cases.length}</span>
                </div>
                <div className="divide-y rounded-md border">
                  {cases.map((c) => (
                    <div
                      key={c.case_id}
                      data-testid="run-case-row"
                      className={cn(
                        "flex items-center gap-3 px-2 py-1.5 text-sm hover:bg-muted/50",
                        openCaseId === c.case_id && "bg-primary/10",
                      )}
                    >
                      {!readOnly && (
                        <Checkbox
                          checked={selected.has(c.case_id)}
                          onCheckedChange={() =>
                            setSelected((prev) => {
                              const n = new Set(prev);
                              if (n.has(c.case_id)) n.delete(c.case_id);
                              else n.add(c.case_id);
                              return n;
                            })
                          }
                          aria-label={`Select ${c.key}`}
                        />
                      )}
                      <button
                        type="button"
                        onClick={() => setOpenCase(c.case_id)}
                        className="flex min-w-0 flex-1 items-center gap-3 text-left"
                      >
                        <span className="w-14 shrink-0 font-mono text-xs text-muted-foreground">{c.key}</span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">{c.title}</span>
                          {c.last_result?.error_message ? (
                            <span className="block truncate font-mono text-xs text-status-failed">
                              {c.last_result.error_message}
                            </span>
                          ) : c.last_result?.comment ? (
                            <span className="block truncate text-xs text-muted-foreground">{c.last_result.comment}</span>
                          ) : null}
                        </span>
                        {c.result_count > 1 && (
                          <span className="shrink-0 text-xs text-muted-foreground">{c.result_count} results</span>
                        )}
                        <PriorityBadge priority={c.priority} className="w-16 shrink-0 justify-center" />
                        <AutomationIcon status={c.automation_status} />
                      </button>
                      {readOnly ? (
                        <StatusBadge status={c.status} className="w-24 justify-center" />
                      ) : (
                        <StatusMenu
                          current={c.status}
                          onPick={(status) => setStatuses.mutate({ ids: [c.case_id], status })}
                        />
                      )}
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      <ExecuteSheet
        runId={runId}
        projectId={projectId}
        runCase={openCase}
        readOnly={readOnly}
        onClose={() => setOpenCase(null)}
        onNext={nextUntested}
      />
      {run && (
        <>
          <NameDialog
            open={dialog === "edit"}
            onOpenChange={(o) => !o && setDialog(null)}
            title="Edit run"
            initialName={run.name}
            initialDescription={run.description}
            onSubmit={async (v) => {
              await api.updateRun(runId, v);
              invalidate();
            }}
          />
          <ConfirmDialog
            open={dialog === "delete"}
            onOpenChange={(o) => !o && setDialog(null)}
            title={`Delete run “${run.name}”?`}
            description="All results recorded in this run will be deleted. Test cases are not affected."
            onConfirm={async () => {
              await api.deleteRun(runId).catch(fail);
              qc.invalidateQueries({ queryKey: ["runs", projectId] });
              qc.invalidateQueries({ queryKey: ["projects"] });
              router.push(`/projects/${projectId}/runs`);
            }}
          />
        </>
      )}
    </main>
  );
}

function StatusMenu({
  current,
  label,
  onPick,
}: {
  current?: ResultStatus;
  label?: string;
  onPick: (s: ResultStatus) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {current ? (
          <button type="button" aria-label={`Status: ${statusLabel[current]}`} className="shrink-0">
            <StatusBadge status={current} className="w-24 justify-center hover:ring-2 hover:ring-ring/30" />
          </button>
        ) : (
          <Button variant="outline" size="sm">
            {label}
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {SETTABLE.map((s) => (
          <DropdownMenuItem key={s} onSelect={() => onPick(s)}>
            <span className={cn("size-2 rounded-full", statusBg[s])} />
            {statusLabel[s]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
