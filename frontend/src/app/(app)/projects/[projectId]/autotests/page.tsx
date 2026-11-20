"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2, Play } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { useCatalog } from "@/components/cases/catalog-sync";
import { AgentStatus, isActive } from "@/components/runs/autotests";
import { timeAgo } from "@/components/runs/run-meta";
import {
  describeParams,
  initialParams,
  optionsAgent,
  rememberedParams,
  rememberParams,
  RunOptionsForm,
} from "@/components/runs/run-options";
import { runnable, TestPicker } from "@/components/runs/test-picker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import type { AutomationJob, JobStatus, RunParams } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS: Record<JobStatus, { label: string; tone: string }> = {
  queued: { label: "Waiting for an agent", tone: "text-muted-foreground" },
  running: { label: "Running", tone: "text-primary" },
  finished: { label: "Finished", tone: "text-status-passed" },
  error: { label: "Failed to run", tone: "text-status-failed" },
  cancelled: { label: "Cancelled", tone: "text-muted-foreground" },
};

const defaultName = () => `Autotests ${new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`;

export default function AutotestsPage() {
  const { projectId: pid } = useParams<{ projectId: string }>();
  const projectId = Number(pid);
  const router = useRouter();
  const qc = useQueryClient();

  const { data: agents } = useQuery({
    queryKey: ["agents", projectId],
    queryFn: () => api.agents(projectId),
    refetchInterval: 5000,
  });
  const runOptions = optionsAgent(agents)?.options ?? [];
  const optionsKey = JSON.stringify(runOptions);
  const [params, setParams] = useState<RunParams>({});
  useEffect(() => {
    setParams(initialParams(runOptions, rememberedParams(projectId)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optionsKey, projectId]);

  const { data: catalog } = useCatalog(projectId);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // Drop picks whose test went away or lost its case.
  useEffect(() => {
    if (!catalog) return;
    const valid = new Set(catalog.items.filter(runnable).map((i) => i.case_id!));
    setSelected((s) => {
      const kept = [...s].filter((id) => valid.has(id));
      return kept.length === s.size ? s : new Set(kept);
    });
  }, [catalog]);

  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const jobsQ = useQuery({
    queryKey: ["autotest-jobs", projectId],
    queryFn: () => api.autotestJobs(projectId),
    refetchInterval: (q) => (q.state.data?.some(isActive) ? 2000 : 10_000),
  });

  const start = async (caseIds: number[]) => {
    setBusy(true);
    try {
      const job = await api.startAutotests(projectId, {
        name: name.trim() || defaultName(),
        case_ids: caseIds,
        params: runOptions.length ? params : {},
      });
      if (runOptions.length) rememberParams(projectId, params);
      toast.success("Autotests queued");
      qc.invalidateQueries({ queryKey: ["autotest-jobs", projectId] });
      qc.invalidateQueries({ queryKey: ["runs", projectId] });
      router.push(`/projects/${projectId}/runs/${job.run_id}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Something went wrong");
      setBusy(false);
    }
  };

  return (
    <main className="h-full overflow-y-auto">
      <div className="mx-auto grid max-w-6xl gap-6 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <section className="grid min-w-0 content-start gap-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <h1 className="text-xl font-semibold">Autotests</h1>
            <Link href={`/projects/${projectId}/autotests/connect`} className="order-last ml-auto text-sm text-primary hover:underline">
              Connect autotests
            </Link>
            {catalog && (
              <span className="text-sm text-muted-foreground">
                {catalog.items.filter((i) => i.action !== "outdated").length} tests from {catalog.agent ?? "an agent"}
                , {timeAgo(catalog.uploaded_at)}
              </span>
            )}
          </div>
          <TestPicker
            projectId={projectId}
            value={selected}
            onChange={setSelected}
            listClassName="max-h-[60vh] lg:max-h-[calc(100dvh-14rem)]"
            onSynced={() => qc.invalidateQueries({ queryKey: ["cases"] })}
          />
        </section>

        <aside className="grid min-w-0 content-start gap-5 lg:sticky lg:top-0">
          <AgentStatus projectId={projectId} />
          <div className="grid gap-2">
            <Label htmlFor="autotests-run-name">Run name</Label>
            <Input
              id="autotests-run-name"
              placeholder={defaultName()}
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={300}
            />
          </div>
          {runOptions.length > 0 && <RunOptionsForm options={runOptions} value={params} onChange={setParams} />}
          <div className="grid gap-2">
            <Button onClick={() => start([...selected])} disabled={busy || selected.size === 0} data-testid="run-selected">
              {busy ? <Loader2 className="animate-spin" /> : <Play />}
              Run selected ({selected.size})
            </Button>
            <Button variant="outline" onClick={() => start([])} disabled={busy}>
              <Bot /> Run all
            </Button>
            {selected.size > 0 && (
              <button type="button" className="text-xs text-muted-foreground hover:underline" onClick={() => setSelected(new Set())}>
                Clear the selection
              </button>
            )}
          </div>
          <RecentJobs jobs={jobsQ.data ?? []} projectId={projectId} options={runOptions} />
        </aside>
      </div>
    </main>
  );
}

function RecentJobs({
  jobs,
  projectId,
  options,
}: {
  jobs: AutomationJob[];
  projectId: number;
  options: Parameters<typeof describeParams>[1];
}) {
  if (!jobs.length) return null;
  return (
    <div className="grid gap-2">
      <h2 className="text-sm font-medium">Recent runs</h2>
      <ul className="grid divide-y rounded-md border text-sm" data-testid="recent-jobs">
        {jobs.map((j) => (
          <li key={j.id}>
            <Link href={`/projects/${projectId}/runs/${j.run_id}`} className="grid gap-0.5 px-3 py-2 hover:bg-muted/50">
              <span className="flex items-center gap-2">
                {isActive(j) && <Loader2 className="size-3.5 animate-spin text-primary" />}
                <span className={cn("font-medium", STATUS[j.status].tone)}>{STATUS[j.status].label}</span>
                <span className="ml-auto text-xs text-muted-foreground">{timeAgo(j.created_at)}</span>
              </span>
              <span className="text-xs text-muted-foreground">
                R{j.run_id} · {j.case_ids.length ? `${j.case_ids.length} tests` : "all tests"}
                {j.requested_by_name && ` · ${j.requested_by_name}`}
              </span>
              {Object.keys(j.params ?? {}).length > 0 && (
                <span className="truncate text-xs text-muted-foreground">{describeParams(j.params, options)}</span>
              )}
              {j.message && j.status !== "running" && (
                <span className={cn("truncate text-xs", j.status === "error" ? "text-status-failed" : "text-muted-foreground")}>
                  {j.message}
                </span>
              )}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
