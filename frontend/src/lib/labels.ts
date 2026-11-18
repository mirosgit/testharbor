import type {
  AutomationComplexity,
  AutomationProgress,
  AutomationStatus,
  CaseState,
  CaseType,
  Priority,
  ResultStatus,
} from "./types";

export const priorityLabel: Record<Priority, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const priorityClass: Record<Priority, string> = {
  critical: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  high: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
  medium: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  low: "bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
};

export const typeLabel: Record<CaseType, string> = {
  functional: "Functional",
  regression: "Regression",
  smoke: "Smoke",
  acceptance: "Acceptance",
  performance: "Performance",
  security: "Security",
  other: "Other",
};

export const automationLabel: Record<AutomationStatus, string> = {
  manual: "Manual",
  automated: "Automated",
  to_be_automated: "To be automated",
};

export const stateLabel: Record<CaseState, string> = {
  draft: "Draft",
  active: "Active",
  pending_review: "Pending review",
  outdated: "Outdated",
  rejected: "Rejected",
};

export const stateClass: Record<CaseState, string> = {
  draft: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  active: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  pending_review: "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  outdated: "bg-zinc-100 text-zinc-500 line-through dark:bg-zinc-800 dark:text-zinc-400",
  rejected: "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
};

export const complexityLabel: Record<AutomationComplexity, string> = {
  not_applicable: "Not applicable",
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const progressLabel: Record<AutomationProgress, string> = {
  not_automated: "Not automated",
  in_progress: "In progress",
  automated: "Automated",
  cannot_be_automated: "Can't be automated",
};

export const statusLabel: Record<ResultStatus, string> = {
  passed: "Passed",
  failed: "Failed",
  blocked: "Blocked",
  skipped: "Skipped",
  retest: "Retest",
  untested: "Untested",
};

/** Solid background per status (progress bars, dots). */
export const statusBg: Record<ResultStatus, string> = {
  passed: "bg-status-passed",
  failed: "bg-status-failed",
  blocked: "bg-status-blocked",
  skipped: "bg-status-skipped",
  retest: "bg-status-retest",
  untested: "bg-status-untested",
};

/** Soft pill style per status. */
export const statusPill: Record<ResultStatus, string> = {
  passed: "bg-status-passed/15 text-status-passed",
  failed: "bg-status-failed/15 text-status-failed",
  blocked: "bg-status-blocked/15 text-status-blocked",
  skipped: "bg-status-skipped/20 text-amber-700 dark:text-amber-400",
  retest: "bg-status-retest/15 text-status-retest",
  untested: "bg-muted text-muted-foreground",
};
