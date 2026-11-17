import type { AutomationStatus, CaseType, Priority, ResultStatus } from "./types";

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
