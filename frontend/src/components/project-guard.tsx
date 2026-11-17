"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { api, ApiError } from "@/lib/api";

/** Shows a friendly message instead of empty screens for unknown project ids. */
export function ProjectGuard({ projectId, children }: { projectId: number; children: React.ReactNode }) {
  const { error } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.project(projectId),
    retry: false,
  });
  if (error instanceof ApiError && error.status === 404) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-muted-foreground">Project #{projectId} doesn&apos;t exist.</p>
        <Link href="/" className="text-primary underline">
          Back to projects
        </Link>
      </div>
    );
  }
  return <>{children}</>;
}
