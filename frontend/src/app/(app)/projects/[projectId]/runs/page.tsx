"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Lock, PlayCircle, Plus, Trash2, Upload } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { CreateRunDialog } from "@/components/runs/create-run-dialog";
import { JUnitUploadDialog } from "@/components/runs/junit-upload-dialog";
import { passRate, percentDone, RunProgress } from "@/components/runs/progress";
import { CiMeta, RunSourceBadge, timeAgo } from "@/components/runs/run-meta";
import { Pager, SortMenu, type SortOption, type SortState } from "@/components/sort-menu";
import { ConfirmDialog } from "@/components/dialogs";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { useIsAdmin } from "@/lib/me";
import type { RunSort } from "@/lib/types";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "open", label: "Open", closed: false },
  { key: "closed", label: "Closed", closed: true },
  { key: "all", label: "All", closed: undefined },
] as const;
const PAGE = 50;
const RUN_SORT_OPTIONS: SortOption<RunSort>[] = [
  { key: "created_at", label: "Created", defaultOrder: "desc" },
  { key: "name", label: "Name" },
  { key: "closed_at", label: "Closed", defaultOrder: "desc" },
];

export default function RunsPage() {
  const { projectId: pid } = useParams<{ projectId: string }>();
  const projectId = Number(pid);
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("all");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<SortState<RunSort>>({ sort: "created_at", order: "desc" });
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const closed = TABS.find((t) => t.key === tab)!.closed;
  const isAdmin = useIsAdmin();
  const qc = useQueryClient();
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [deleting, setDeleting] = useState(false);
  useEffect(() => setPicked(new Set()), [tab, page, sort]);
  const { data, isLoading } = useQuery({
    queryKey: ["runs", projectId, tab, page, sort],
    queryFn: () => api.runs(projectId, { closed, limit: PAGE, offset: page * PAGE, ...sort }),
    placeholderData: (prev) => prev,
  });

  const allPicked = !!data?.items.length && data.items.every((r) => picked.has(r.id));

  return (
    <main className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl p-6">
        <div className="mb-4 flex items-center gap-4">
          <h1 className="text-xl font-semibold">Test runs</h1>
          <div className="flex rounded-md border p-0.5 text-sm">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => {
                  setTab(t.key);
                  setPage(0);
                }}
                className={cn(
                  "rounded px-3 py-1 text-muted-foreground",
                  tab === t.key && "bg-muted font-medium text-foreground",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="ml-auto">
            <SortMenu
              options={RUN_SORT_OPTIONS}
              value={sort}
              onChange={(v) => {
                setSort(v);
                setPage(0);
              }}
            />
          </div>
          <Button size="sm" variant="outline" asChild>
            <Link href={`/projects/${projectId}/autotests`}>
              <Bot /> Run autotests
            </Link>
          </Button>
          <Button size="sm" variant="outline" onClick={() => setUploading(true)}>
            <Upload /> Upload JUnit
          </Button>
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus /> New run
          </Button>
        </div>

        {isLoading ? (
          <div className="grid gap-2">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : !data?.items.length ? (
          <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-16 text-center">
            <PlayCircle className="size-10 text-muted-foreground" />
            <p className="text-muted-foreground">
              No runs here yet. Create one manually, or upload JUnit results from CI.
            </p>
            <Button onClick={() => setCreating(true)}>
              <Plus /> New run
            </Button>
          </div>
        ) : (
          <div className="divide-y rounded-lg border" data-testid="runs-list">
            {isAdmin && (
              <div className="flex min-h-11 flex-wrap items-center gap-3 bg-muted/30 px-4 py-2 text-sm">
                <Checkbox
                  aria-label="Select all runs on this page"
                  checked={allPicked ? true : picked.size ? "indeterminate" : false}
                  onCheckedChange={(v) => setPicked(v === true ? new Set(data.items.map((r) => r.id)) : new Set())}
                />
                {picked.size ? (
                  <>
                    <span className="font-medium">{picked.size} selected</span>
                    <Button size="xs" variant="destructive" onClick={() => setDeleting(true)}>
                      <Trash2 /> Delete
                    </Button>
                    <Button size="xs" variant="ghost" onClick={() => setPicked(new Set())}>
                      Clear
                    </Button>
                  </>
                ) : (
                  <span className="text-muted-foreground">Select runs to delete them</span>
                )}
              </div>
            )}
            {data.items.map((r) => (
              <div
                key={r.id}
                className={cn(
                  "relative grid items-center gap-6 px-4 py-3 hover:bg-muted/40",
                  isAdmin ? "grid-cols-[auto_1fr_260px_110px]" : "grid-cols-[1fr_260px_110px]",
                  picked.has(r.id) && "bg-primary/5",
                )}
                data-testid="run-row"
              >
                <Link href={`/projects/${projectId}/runs/${r.id}`} className="absolute inset-0" aria-label={r.name} />
                {isAdmin && (
                  <Checkbox
                    className="relative z-10"
                    aria-label={`Select ${r.name}`}
                    checked={picked.has(r.id)}
                    onCheckedChange={(v) =>
                      setPicked((s) => {
                        const n = new Set(s);
                        if (v === true) n.add(r.id);
                        else n.delete(r.id);
                        return n;
                      })
                    }
                  />
                )}
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <RunSourceBadge run={r} />
                    <span className="truncate font-medium">{r.name}</span>
                    {r.closed && <Lock className="size-3.5 text-muted-foreground" aria-label="Closed" />}
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                    <span>R{r.id}</span>
                    <span>{timeAgo(r.created_at)}</span>
                    <CiMeta run={r} />
                  </div>
                </div>
                <div className="grid gap-1.5">
                  <RunProgress stats={r.stats} />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>
                      <span className="text-status-passed">{r.stats.passed} passed</span>
                      {r.stats.failed > 0 && <span className="text-status-failed"> · {r.stats.failed} failed</span>}
                      {r.stats.blocked > 0 && <span> · {r.stats.blocked} blocked</span>}
                    </span>
                    <span>{r.stats.untested} untested</span>
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-semibold tabular-nums">{passRate(r.stats)}%</div>
                  <div className="text-xs text-muted-foreground">
                    passed · {percentDone(r.stats)}% done
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        {data && (
          <div className="mt-4">
            <Pager page={page} pageSize={PAGE} total={data.total} onPage={setPage} sizes={[PAGE]} />
          </div>
        )}
      </div>
      <CreateRunDialog open={creating} onOpenChange={setCreating} projectId={projectId} />
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Delete ${picked.size} run${picked.size === 1 ? "" : "s"}?`}
        description="All results recorded in them are deleted, and running autotests are stopped. Test cases are not affected."
        onConfirm={async () => {
          try {
            const { deleted } = await api.deleteRuns(projectId, [...picked]);
            toast.success(`${deleted} run${deleted === 1 ? "" : "s"} deleted`);
            setPicked(new Set());
            qc.invalidateQueries({ queryKey: ["runs", projectId] });
          } catch (e) {
            toast.error(e instanceof ApiError ? e.message : "Something went wrong");
          }
        }}
      />
      <JUnitUploadDialog open={uploading} onOpenChange={setUploading} projectId={projectId} />
    </main>
  );
}
