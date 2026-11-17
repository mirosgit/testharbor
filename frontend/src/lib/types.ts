export type Priority = "low" | "medium" | "high" | "critical";
export type CaseType =
  | "functional"
  | "regression"
  | "smoke"
  | "acceptance"
  | "performance"
  | "security"
  | "other";
export type AutomationStatus = "manual" | "automated" | "to_be_automated";
export type ResultStatus = "passed" | "failed" | "blocked" | "skipped" | "retest" | "untested";
export type RunSource = "manual" | "ci";

export const PRIORITIES: Priority[] = ["critical", "high", "medium", "low"];
export const CASE_TYPES: CaseType[] = [
  "functional",
  "regression",
  "smoke",
  "acceptance",
  "performance",
  "security",
  "other",
];
export const AUTOMATION_STATUSES: AutomationStatus[] = ["manual", "automated", "to_be_automated"];
export const RESULT_STATUSES: ResultStatus[] = [
  "passed",
  "failed",
  "blocked",
  "retest",
  "skipped",
  "untested",
];

export interface Project {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  suite_count: number;
  case_count: number;
  run_count: number;
}

export interface Suite {
  id: number;
  project_id: number;
  name: string;
  description: string;
  case_count: number;
}

export interface Section {
  id: number;
  suite_id: number;
  parent_id: number | null;
  name: string;
  description: string;
  position: number;
  case_count: number;
}

export interface Step {
  action: string;
  expected: string;
}

export interface TestCase {
  id: number;
  key: string;
  project_id: number;
  suite_id: number;
  section_id: number;
  title: string;
  preconditions: string;
  steps: Step[];
  expected_result: string;
  priority: Priority;
  type: CaseType;
  tags: string[];
  automation_status: AutomationStatus;
  automation_key: string | null;
  position: number;
  created_at: string;
  updated_at: string;
}

export type CaseInput = Omit<
  TestCase,
  "id" | "key" | "project_id" | "suite_id" | "position" | "created_at" | "updated_at"
>;

export interface CaseList {
  items: TestCase[];
  total: number;
}

export interface CaseFilter {
  suite_id?: number;
  section_id?: number;
  q?: string;
  tags?: string[];
  priority?: Priority[];
  type?: CaseType[];
  automation_status?: AutomationStatus[];
}

export interface ImportResult {
  created: number;
  updated: number;
  sections_created: number;
  errors: string[];
}
