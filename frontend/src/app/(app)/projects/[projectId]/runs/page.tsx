"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Lock, PlayCircle, Plus, Upload } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { RunAutotestsDialog } from "@/components/runs/autotests";
import { CreateRunDialog } from "@/components/runs/create-run-dialog";
import { JUnitUploadDialog } from "@/components/runs/junit-upload-dialog";
import { passRate, percentDone, RunProgress } from "@/components/runs/progress";
import { CiMeta, RunSourceBadge, timeAgo } from "@/components/runs/run-meta";
import { Pager, SortMenu, type SortOption, type SortState } from "@/components/sort-menu";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
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
  const [autotests, setAutotests] = useState(false);
  const closed = TABS.find((t) => t.key === tab)!.closed;
  const { data, isLoading } = useQuery({
    queryKey: ["runs", projectId, tab, page, sort],
    queryFn: () => api.runs(projectId, { closed, limit: PAGE, offset: page * PAGE, ...sort }),
    placeholderData: (prev) => prev,
  });

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
          <Button size="sm" variant="outline" onClick={() => setAutotests(true)}>
            <Bot /> Run autotests
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
            {data.items.map((r) => (
              <div key={r.id} className="relative grid grid-cols-[1fr_260px_110px] items-center gap-6 px-4 py-3 hover:bg-muted/40">
                <Link href={`/projects/${projectId}/runs/${r.id}`} className="absolute inset-0" aria-label={r.name} />
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
      <RunAutotestsDialog open={autotests} onOpenChange={setAutotests} projectId={projectId} target={{ kind: "new" }} />
      <CreateRunDialog open={creating} onOpenChange={setCreating} projectId={projectId} />
      <JUnitUploadDialog open={uploading} onOpenChange={setUploading} projectId={projectId} />
    </main>
  );
}
