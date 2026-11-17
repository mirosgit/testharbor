"use client";

import { useQuery } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/badges";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

export function CaseHistory({ caseId, projectId }: { caseId: number; projectId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["case-history", caseId],
    queryFn: () => api.caseHistory(caseId),
  });
  return (
    <section data-testid="case-history">
      <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Run history</h3>
      {isLoading ? (
        <Skeleton className="h-16" />
      ) : !data?.length ? (
        <p className="text-sm text-muted-foreground">This case hasn&apos;t been in any test run yet.</p>
      ) : (
        <ul className="divide-y rounded-md border text-sm">
          {data.map((h) => (
            <li key={h.run_id} className="flex items-center gap-3 px-3 py-2">
              <StatusBadge status={h.status} className="w-20 justify-center" />
              <div className="min-w-0 flex-1">
                <Link
                  href={`/projects/${projectId}/runs/${h.run_id}?case=${caseId}`}
                  className="block truncate font-medium hover:underline"
                >
                  {h.run_name}
                </Link>
                {h.last_result?.error_message && (
                  <p className="truncate font-mono text-xs text-status-failed">{h.last_result.error_message}</p>
                )}
                {h.last_result?.comment && !h.last_result.error_message && (
                  <p className="truncate text-xs text-muted-foreground">{h.last_result.comment}</p>
                )}
              </div>
              {h.branch && (
                <span className="hidden items-center gap-1 text-xs text-muted-foreground sm:inline-flex">
                  <GitBranch className="size-3" />
                  {h.branch}
                </span>
              )}
              <span className="shrink-0 text-right text-xs text-muted-foreground">
                {new Date(h.last_result?.created_at ?? h.run_created_at).toLocaleDateString()}
                {h.last_result?.recorded_by && <span className="block">{h.last_result.recorded_by}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
