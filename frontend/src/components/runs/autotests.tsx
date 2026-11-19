"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Copy, Loader2, Play, Square } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { api, ApiError } from "@/lib/api";
import type { AutomationJob, JobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACTIVE: JobStatus[] = ["queued", "running"];
export const isActive = (j?: AutomationJob | null) => !!j && ACTIVE.includes(j.status);

const fail = (e: unknown) => toast.error(e instanceof ApiError ? e.message : "Something went wrong");

/** Shows whether an agent is polling this project, and how to start one if not. */
export function AgentStatus({ projectId }: { projectId: number }) {
  const { data: agents, isLoading } = useQuery({
    queryKey: ["agents", projectId],
    queryFn: () => api.agents(projectId),
    refetchInterval: 5000,
  });
  const online = agents?.filter((a) => a.online) ?? [];
  if (isLoading) return null;
  if (online.length)
    return (
      <p className="flex items-center gap-2 text-sm" data-testid="agent-status">
        <span className="size-2 rounded-full bg-status-passed" />
        Agent online: <b>{online.map((a) => a.name).join(", ")}</b>
      </p>
    );
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const setup = [
    `export TESTHARBOR_URL=${origin}`,
    "export TESTHARBOR_TOKEN=<your API token>",
    `testcli agent --project ${projectId} --report-url http://localhost:9323/index.html`,
  ].join("\n");
  return (
    <div className="grid min-w-0 gap-2 rounded-md border border-amber-400 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/40" data-testid="agent-status">
      <p className="flex items-start gap-2 font-medium">
        <span className="mt-1.5 size-2 shrink-0 rounded-full bg-status-skipped" />
        No agent is online. The job will wait until one starts.
      </p>
      <p className="text-xs text-muted-foreground">
        In the folder with the Playwright tests (JSON reporter writing <code>reports/results.json</code>), run the
        commands below. A token is created in{" "}
        <Link href="/settings/tokens" className="underline">
          API tokens
        </Link>
        .
      </p>
      <div className="relative min-w-0">
        <pre className="overflow-x-auto rounded border bg-background p-2 pr-9 font-mono text-[11px] leading-relaxed">{setup}</pre>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute top-1 right-1"
          aria-label="Copy commands"
          onClick={() => {
            void navigator.clipboard?.writeText(setup);
            toast.success("Copied");
          }}
        >
          <Copy />
        </Button>
      </div>
    </div>
  );
}

type Scope = "all" | "selected" | "failed";

export type AutotestsTarget =
  | { kind: "new"; caseIds?: number[] }
  | { kind: "run"; runId: number; failedCount: number; selectedIds: number[] };

export function RunAutotestsDialog({
  open,
  onOpenChange,
  projectId,
  target,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  projectId: number;
  target: AutotestsTarget;
}) {
  const router = useRouter();
  const qc = useQueryClient();
  const selectedCount = target.kind === "new" ? (target.caseIds?.length ?? 0) : target.selectedIds.length;
  const [scope, setScope] = useState<Scope>("all");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const runRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    setScope(selectedCount ? "selected" : "all");
    setName(`Autotests ${new Date().toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const options: { value: Scope; label: string; hint: string; show: boolean }[] = [
    { value: "all", label: "All autotests", hint: "Runs the whole test suite", show: true },
    {
      value: "selected",
      label: "Selected cases",
      hint: `${selectedCount} cases, matched by C-ID in test titles or tags`,
      show: selectedCount > 0,
    },
    {
      value: "failed",
      label: "Failed cases",
      hint: target.kind === "run" ? `${target.failedCount} cases` : "",
      show: target.kind === "run" && target.failedCount > 0,
    },
  ];

  const start = async () => {
    setBusy(true);
    try {
      const caseIds = target.kind === "new" ? (target.caseIds ?? []) : target.selectedIds;
      const job = await api.startAutotests(projectId, {
        ...(target.kind === "run" ? { run_id: target.runId } : { name: name.trim() || undefined }),
        case_ids: scope === "selected" ? caseIds : [],
        only_failed: scope === "failed",
      });
      toast.success("Autotests queued");
      qc.invalidateQueries({ queryKey: ["autotest-jobs", projectId] });
      qc.invalidateQueries({ queryKey: ["runs", projectId] });
      onOpenChange(false);
      if (target.kind === "new") router.push(`/projects/${projectId}/runs/${job.run_id}`);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-lg"
        onOpenAutoFocus={(e) => {
          // Radix focuses (and selects) the first input; the primary action is the better start.
          e.preventDefault();
          runRef.current?.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle>Run autotests</DialogTitle>
          <DialogDescription>
            An agent on the machine with the tests runs them and uploads the results
            {target.kind === "run" ? " into this run." : " into a new run."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <AgentStatus projectId={projectId} />
          {target.kind === "new" && (
            <div className="grid gap-2">
              <Label htmlFor="autotests-name">Run name</Label>
              <Input id="autotests-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={300} />
            </div>
          )}
          <fieldset className="grid gap-2">
            <legend className="mb-2 text-sm font-medium">What to run</legend>
            {options
              .filter((o) => o.show)
              .map((o) => (
                <label
                  key={o.value}
                  className={cn(
                    "flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 text-sm",
                    scope === o.value && "border-primary bg-primary/5",
                  )}
                >
                  <input
                    type="radio"
                    name="autotests-scope"
                    checked={scope === o.value}
                    onChange={() => setScope(o.value)}
                    className="shrink-0 accent-primary"
                  />
                  <span className="grid min-w-0 flex-1">
                    <span>{o.label}</span>
                    {o.hint && <span className="text-xs text-muted-foreground">{o.hint}</span>}
                  </span>
                </label>
              ))}
          </fieldset>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button ref={runRef} onClick={start} disabled={busy}>
            <Play /> {busy ? "Starting…" : "Run"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const statusText: Record<JobStatus, string> = {
  queued: "Waiting for an agent",
  running: "Running",
  finished: "Finished",
  error: "Failed to run",
  cancelled: "Cancelled",
};

function elapsed(job: AutomationJob, now: number): string {
  if (!job.started_at) return "";
  const end = job.finished_at ? new Date(job.finished_at).getTime() : now;
  const s = Math.max(0, Math.round((end - new Date(job.started_at).getTime()) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** Latest autotest job of a run: status, live log, cancel. */
export function AutotestsPanel({
  projectId,
  runId,
  onDone,
}: {
  projectId: number;
  runId: number;
  /** Called when a job stops (results were uploaded). */
  onDone: () => void;
}) {
  const qc = useQueryClient();
  const jobsQ = useQuery({
    queryKey: ["autotest-jobs", projectId, runId],
    queryFn: () => api.autotestJobs(projectId, runId),
    refetchInterval: (q) => (isActive(q.state.data?.[0]) ? 2000 : false),
  });
  const latest = jobsQ.data?.[0];
  const active = isActive(latest);
  const detailQ = useQuery({
    queryKey: ["autotest-job", latest?.id],
    queryFn: () => api.autotestJob(latest!.id),
    enabled: !!latest,
    refetchInterval: active ? 2000 : false,
  });
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);

  // When a job stops, refresh the run's results and the job's final log.
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !active) {
      onDone();
      void detailQ.refetch();
    }
    wasActive.current = active;
  }, [active, onDone, detailQ]);

  const logRef = useRef<HTMLPreElement>(null);
  const log = detailQ.data?.log ?? "";
  useEffect(() => {
    const el = logRef.current;
    if (el && active) el.scrollTop = el.scrollHeight;
  }, [log, active]);

  if (!latest) return null;
  const job = detailQ.data ?? latest;
  const tone =
    job.status === "finished"
      ? "border-status-passed/40"
      : job.status === "error"
        ? "border-status-failed/50"
        : job.status === "cancelled"
          ? ""
          : "border-primary/40";

  return (
    <section className={cn("mb-4 rounded-lg border p-3", tone)} data-testid="autotests-panel">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        {active ? <Loader2 className="size-4 animate-spin text-primary" /> : <Bot className="size-4 text-muted-foreground" />}
        <span className="font-medium" data-testid="autotests-status">
          Autotests: {statusText[job.status]}
        </span>
        <span className="text-muted-foreground">
          {job.case_ids.length ? `${job.case_ids.length} cases` : "all tests"}
          {job.agent && ` · ${job.agent}`}
          {job.started_at && ` · ${elapsed(job, now)}`}
          {job.exit_code != null && ` · exit ${job.exit_code}`}
          {job.requested_by_name && ` · started by ${job.requested_by_name}`}
        </span>
        {active && (
          <Button
            size="xs"
            variant="outline"
            className="ml-auto"
            onClick={async () => {
              await api.cancelAutotests(job.id).catch(fail);
              qc.invalidateQueries({ queryKey: ["autotest-jobs", projectId, runId] });
            }}
          >
            <Square /> Cancel
          </Button>
        )}
      </div>
      {job.message && (
        <p className={cn("mt-1 text-sm", job.status === "error" ? "text-status-failed" : "text-muted-foreground")}>
          {job.message}
        </p>
      )}
      {job.status === "queued" && (
        <div className="mt-3">
          <AgentStatus projectId={projectId} />
        </div>
      )}
      {log && (
        <details className="mt-2" open={active}>
          <summary className="cursor-pointer text-xs text-muted-foreground">Output</summary>
          <pre
            ref={logRef}
            className="mt-1 max-h-80 overflow-auto rounded bg-muted p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap"
            data-testid="autotests-log"
          >
            {log}
          </pre>
        </details>
      )}
    </section>
  );
}
