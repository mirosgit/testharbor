"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PriorityBadge, StatusBadge } from "@/components/badges";
import { Markdown } from "@/components/markdown";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { statusBg, statusLabel } from "@/lib/labels";
import type { ResultStatus, RunCase, TestResult } from "@/lib/types";
import { cn } from "@/lib/utils";

const SETTABLE: ResultStatus[] = ["passed", "failed", "blocked", "retest", "skipped"];

export function ExecuteSheet({
  runId,
  projectId,
  runCase,
  readOnly,
  onClose,
  onNext,
}: {
  runId: number;
  projectId: number;
  runCase: RunCase | null;
  readOnly: boolean;
  onClose: () => void;
  /** Move on to the next untested case (if any). */
  onNext: () => void;
}) {
  return (
    <Sheet open={!!runCase} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-3xl" data-testid="execute-sheet">
        {runCase && (
          <ExecuteBody
            key={runCase.case_id}
            runId={runId}
            projectId={projectId}
            rc={runCase}
            readOnly={readOnly}
            onNext={onNext}
          />
        )}
      </SheetContent>
    </Sheet>
  );
}

function ExecuteBody({
  runId,
  projectId,
  rc,
  readOnly,
  onNext,
}: {
  runId: number;
  projectId: number;
  rc: RunCase;
  readOnly: boolean;
  onNext: () => void;
}) {
  const qc = useQueryClient();
  const { data: testCase } = useQuery({ queryKey: ["case", rc.case_id], queryFn: () => api.case(rc.case_id) });
  const { data: results, isLoading } = useQuery({
    queryKey: ["run-results", runId, rc.case_id],
    queryFn: () => api.caseResultsInRun(runId, rc.case_id),
  });
  const [status, setStatus] = useState<ResultStatus | null>(null);
  const [comment, setComment] = useState("");
  useEffect(() => {
    setStatus(null);
    setComment("");
  }, [rc.case_id]);

  const save = useMutation({
    mutationFn: () => api.addResult(runId, { case_id: rc.case_id, status: status!, comment: comment.trim() || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["run", runId] });
      qc.invalidateQueries({ queryKey: ["run-cases", runId] });
      qc.invalidateQueries({ queryKey: ["run-results", runId, rc.case_id] });
      qc.invalidateQueries({ queryKey: ["case-history", rc.case_id] });
      qc.invalidateQueries({ queryKey: ["runs", projectId] });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "Could not save result"),
  });

  const submit = async (next: boolean) => {
    await save.mutateAsync();
    toast.success(`${rc.key}: ${statusLabel[status!]}`);
    setStatus(null);
    setComment("");
    if (next) onNext();
  };

  return (
    <>
      <SheetHeader className="border-b pr-12">
        <SheetDescription className="flex items-center gap-2 text-xs">
          <span className="font-mono">{rc.key}</span>· {rc.section_path.replaceAll(" > ", " › ")}
        </SheetDescription>
        <SheetTitle className="text-lg leading-snug">{rc.title}</SheetTitle>
        <div className="flex items-center gap-2 pt-1 text-sm">
          <span className="text-muted-foreground">Current:</span>
          <StatusBadge status={rc.status} />
          <PriorityBadge priority={rc.priority} />
          <Link
            href={`/projects/${projectId}/cases?suite=${rc.suite_id}&case=${rc.case_id}`}
            className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            Open case <ExternalLink className="size-3" />
          </Link>
        </div>
      </SheetHeader>

      <div className="grid gap-6 p-6">
        {!readOnly && (
          <section className="grid gap-3 rounded-lg border bg-muted/30 p-4" aria-label="Add result">
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Result status">
              {SETTABLE.map((s) => (
                <button
                  key={s}
                  type="button"
                  role="radio"
                  aria-checked={status === s}
                  onClick={() => setStatus(s)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-md border bg-background px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted",
                    status === s && "border-transparent text-white",
                    status === s && statusBg[s],
                  )}
                >
                  <span className={cn("size-2 rounded-full", statusBg[s], status === s && "bg-primary-foreground")} />
                  {statusLabel[s]}
                </button>
              ))}
            </div>
            <Textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Comment (optional, markdown)…"
              rows={2}
              aria-label="Comment"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && status) void submit(false);
              }}
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" disabled={!status || save.isPending} onClick={() => void submit(true)}>
                Save &amp; next untested
              </Button>
              <Button size="sm" disabled={!status || save.isPending} onClick={() => void submit(false)}>
                Add result
              </Button>
            </div>
          </section>
        )}

        {!testCase ? (
          <Skeleton className="h-32" />
        ) : (
          <>
            {testCase.preconditions.trim() && (
              <Block title="Preconditions">
                <Markdown>{testCase.preconditions}</Markdown>
              </Block>
            )}
            {testCase.steps.length > 0 && (
              <Block title="Steps">
                <ol className="divide-y rounded-md border">
                  {testCase.steps.map((s, i) => (
                    <li key={i} className="grid grid-cols-[2rem_1fr_1fr] gap-3 px-3 py-2.5">
                      <span className="text-sm text-muted-foreground tabular-nums">{i + 1}</span>
                      <Markdown>{s.action}</Markdown>
                      <div className="text-muted-foreground">
                        <Markdown>{s.expected}</Markdown>
                      </div>
                    </li>
                  ))}
                </ol>
              </Block>
            )}
            {testCase.expected_result.trim() && (
              <Block title="Expected result">
                <Markdown>{testCase.expected_result}</Markdown>
              </Block>
            )}
          </>
        )}

        <Block title="Results in this run">
          {isLoading ? (
            <Skeleton className="h-12" />
          ) : !results?.length ? (
            <p className="text-sm text-muted-foreground">No results yet.</p>
          ) : (
            <ul className="grid gap-2" data-testid="run-results">
              {results.map((r) => (
                <ResultItem key={r.id} r={r} />
              ))}
            </ul>
          )}
        </Block>
      </div>
    </>
  );
}

export function ResultItem({ r }: { r: TestResult }) {
  return (
    <li className="rounded-md border p-3 text-sm">
      <div className="flex items-center gap-2">
        <StatusBadge status={r.status} />
        {r.duration_ms != null && (
          <span className="text-xs text-muted-foreground">{(r.duration_ms / 1000).toFixed(2)}s</span>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          {r.recorded_by && <>{r.recorded_by} · </>}
          {new Date(r.created_at).toLocaleString()}
        </span>
      </div>
      {r.error_message && (
        <p className="mt-2 font-mono text-xs break-words whitespace-pre-wrap text-status-failed">{r.error_message}</p>
      )}
      {r.comment && <Markdown className="mt-2">{r.comment}</Markdown>}
      {r.stack_trace && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-muted-foreground">Stack trace / log</summary>
          <pre className="mt-1 max-h-72 overflow-auto rounded bg-muted p-2 font-mono text-[11px] leading-relaxed">
            {r.stack_trace}
          </pre>
        </details>
      )}
    </li>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  );
}
