import { Bot, ExternalLink, FileText, GitBranch, GitCommit, User } from "lucide-react";

import type { TestRun } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Opens a test's page in the run's HTML report (new tab). */
export function ReportLink({ href, label, className }: { href: string; label: string; className?: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      aria-label={label}
      title={label}
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "inline-flex items-center gap-1 rounded text-xs text-muted-foreground hover:text-foreground hover:underline",
        className,
      )}
    >
      <FileText className="size-3.5" />
    </a>
  );
}

export function RunSourceBadge({ run }: { run: TestRun }) {
  return run.source === "ci" ? (
    <span className="inline-flex items-center gap-1 rounded bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
      <Bot className="size-3" /> CI
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
      <User className="size-3" /> Manual
    </span>
  );
}

export function CiMeta({ run, report = true }: { run: TestRun; report?: boolean }) {
  if (!run.branch && !run.commit && !run.build_url && !(report && run.report_url)) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {run.branch && (
        <span className="inline-flex items-center gap-1">
          <GitBranch className="size-3" />
          {run.branch}
        </span>
      )}
      {run.commit && (
        <span className="inline-flex items-center gap-1 font-mono">
          <GitCommit className="size-3" />
          {run.commit.slice(0, 10)}
        </span>
      )}
      {run.build_url && (
        <a
          href={run.build_url}
          target="_blank"
          rel="noreferrer"
          className="relative z-10 inline-flex items-center gap-1 hover:text-foreground hover:underline"
        >
          <ExternalLink className="size-3" />
          Build
        </a>
      )}
      {report && run.report_url && (
        <a
          href={run.report_url}
          target="_blank"
          rel="noreferrer noopener"
          className="relative z-10 inline-flex items-center gap-1 hover:text-foreground hover:underline"
        >
          <FileText className="size-3" />
          Report
        </a>
      )}
    </span>
  );
}

export function timeAgo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return new Date(iso).toLocaleDateString();
}
