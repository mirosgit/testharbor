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
  external_id: string | null;
  position: number;
  created_at: string;
  updated_at: string;
}

export type CaseInput = Omit<
  TestCase,
  "id" | "key" | "project_id" | "suite_id" | "position" | "created_at" | "updated_at" | "external_id"
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
  warnings: string[];
  ignored_columns: string[];
  section_id: number | null;
}

export interface ImportTarget {
  section_id?: number;
  new_section?: string;
  keep_paths: boolean;
}

export interface RunStats {
  total: number;
  passed: number;
  failed: number;
  blocked: number;
  skipped: number;
  retest: number;
  untested: number;
}

export interface TestRun {
  id: number;
  project_id: number;
  name: string;
  description: string;
  source: RunSource;
  branch: string | null;
  commit: string | null;
  build_url: string | null;
  closed: boolean;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  created_by_name: string | null;
  stats: RunStats;
}

export interface RunList {
  items: TestRun[];
  total: number;
}

export interface TestResult {
  id: number;
  run_id: number;
  case_id: number;
  status: ResultStatus;
  comment: string | null;
  duration_ms: number | null;
  error_message: string | null;
  stack_trace: string | null;
  recorded_by: string | null;
  created_at: string;
}

export interface RunCase {
  case_id: number;
  key: string;
  title: string;
  priority: Priority;
  automation_status: AutomationStatus;
  suite_id: number;
  section_id: number;
  section_path: string;
  status: ResultStatus;
  result_count: number;
  last_result: TestResult | null;
}

export interface RunSelection {
  case_ids?: number[];
  suite_id?: number;
  section_ids?: number[];
  filter?: CaseFilter;
}

export interface ResultInput {
  case_id: number;
  status: ResultStatus;
  comment?: string | null;
  duration_ms?: number | null;
  error_message?: string | null;
}

export interface CaseHistoryItem {
  run_id: number;
  run_name: string;
  run_source: RunSource;
  run_closed: boolean;
  run_created_at: string;
  branch: string | null;
  status: ResultStatus;
  result_count: number;
  last_result: TestResult | null;
}

export interface ApiToken {
  id: number;
  user_id: number;
  owner: string | null;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface JUnitImportResult {
  run_id: number;
  run_name: string;
  total: number;
  matched: number;
  created: number;
  unmatched: { name: string; classname: string; reason: string }[];
  statuses: Record<string, number>;
}

export type Role = "admin" | "tester";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Me extends User {
  via: "session" | "token";
}

export interface AdminUser extends User {
  locked: boolean;
}

export interface Invite {
  id: number;
  purpose: "invite" | "reset";
  email: string;
  role: Role;
  expires_at: string;
  created_at: string;
}

export interface InviteLink extends Invite {
  token: string;
  path: string;
}

export interface InviteInfo {
  purpose: "invite" | "reset";
  email: string;
  role: Role;
  name: string | null;
  expires_at: string;
}
