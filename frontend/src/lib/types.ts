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
export type CaseState = "draft" | "active" | "pending_review" | "outdated" | "rejected";
export type AutomationComplexity = "not_applicable" | "low" | "medium" | "high";
export type AutomationProgress = "not_automated" | "in_progress" | "automated" | "cannot_be_automated";
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
export const CASE_STATES: CaseState[] = ["draft", "active", "pending_review", "outdated", "rejected"];
export const AUTOMATION_COMPLEXITIES: AutomationComplexity[] = ["not_applicable", "low", "medium", "high"];
export const AUTOMATION_PROGRESSES: AutomationProgress[] = [
  "not_automated",
  "in_progress",
  "automated",
  "cannot_be_automated",
];
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
  /** Roles to pick from when marking which user roles a case applies to. */
  roles: string[];
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

export interface CustomField {
  name: string;
  value: string;
}

export interface FieldValues {
  name: string;
  values: string[];
}

/** Fields to overwrite on many cases at once; omitted = unchanged, null = clear. */
export interface CaseBulkUpdate {
  case_ids: number[];
  set?: Partial<{
    priority: Priority;
    type: CaseType;
    automation_status: AutomationStatus;
    state: CaseState;
    owner: string | null;
    sprint: string | null;
    automation_complexity: AutomationComplexity | null;
    automation_progress: AutomationProgress | null;
  }>;
  add_tags?: string[];
  remove_tags?: string[];
  add_roles?: string[];
  remove_roles?: string[];
}

/** Owners, sprints and roles in use in a project (owners include active users). */
export interface CaseValues {
  owners: string[];
  sprints: string[];
  roles: string[];
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
  description: string;
  preconditions: string;
  steps: Step[];
  expected_result: string;
  priority: Priority;
  type: CaseType;
  tags: string[];
  automation_status: AutomationStatus;
  automation_key: string | null;
  /** Created from the autotests' catalog: its text follows the test. */
  catalog_managed?: boolean;
  external_id: string | null;
  state: CaseState;
  owner: string | null;
  automation_complexity: AutomationComplexity | null;
  automation_progress: AutomationProgress | null;
  sprint: string | null;
  roles: string[];
  custom_fields: CustomField[];
  position: number;
  created_at: string;
  updated_at: string;
  updated_by: string | null;
}

export type CaseInput = Omit<
  TestCase,
  "id" | "key" | "project_id" | "suite_id" | "position" | "created_at" | "updated_at" | "updated_by" | "external_id"
>;

export interface CaseList {
  items: TestCase[];
  total: number;
}

export type CaseSort =
  | "manual"
  | "id"
  | "title"
  | "priority"
  | "type"
  | "state"
  | "automation_status"
  | "owner"
  | "sprint"
  | "created_at"
  | "updated_at";
export type RunSort = "created_at" | "name" | "closed_at";

export interface CaseFilter {
  suite_id?: number;
  section_id?: number;
  q?: string;
  tags?: string[];
  priority?: Priority[];
  type?: CaseType[];
  automation_status?: AutomationStatus[];
  state?: CaseState[];
  automation_complexity?: AutomationComplexity[];
  automation_progress?: AutomationProgress[];
  owner?: string[];
  sprint?: string[];
  roles?: string[];
  /** Custom field name -> accepted values. */
  fields?: Record<string, string[]>;
}

export interface ImportResult {
  created: number;
  updated: number;
  sections_created: number;
  errors: string[];
  warnings: string[];
  ignored_columns: string[];
  extra_columns: { name: string; selected: boolean }[];
  section_id: number | null;
  dry_run: boolean;
}

export interface ImportTarget {
  section_id?: number;
  new_section?: string;
  keep_paths: boolean;
  /** Extra columns to keep as custom fields; undefined = server default. */
  columns?: string[];
  dry_run?: boolean;
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
  /** HTML report of the run (e.g. Playwright's index.html). */
  report_url: string | null;
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
  /** The configuration the test ran in, e.g. a role or a browser ("Super Admin"). */
  config: string | null;
  created_at: string;
  /** This result's details in the run's HTML report. */
  report_link: string | null;
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

// --- Automation jobs (run tests from TestHarbor via `testcli agent`) ---

export type JobStatus = "queued" | "running" | "finished" | "error" | "cancelled";

export interface AutomationJob {
  id: number;
  project_id: number;
  run_id: number;
  status: JobStatus;
  /** Only these cases; empty = all tests. */
  case_ids: number[];
  /** Values of the agent's run options (environment variables of its command). */
  params: RunParams;
  /** Only this agent may take the job. */
  target_agent: string | null;
  /** The git branch a server agent runs. */
  branch: string | null;
  agent: string | null;
  exit_code: number | null;
  message: string | null;
  requested_by_name: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AutomationJobDetail extends AutomationJob {
  log: string;
}

export type RunParamValue = string | boolean | string[];
export type RunParams = Record<string, RunParamValue>;

/** A run option an agent offers (its --options file): an environment variable of its command. */
export interface AgentOption {
  name: string;
  label: string;
  type: "choice" | "multi" | "bool";
  choices: { value: string; label: string }[];
  default?: RunParamValue | null;
  hint?: string | null;
}

/** Where an agent runs the tests from. */
export interface AgentInfo {
  mode?: "local" | "repo" | null;
  folder?: string | null;
  branch?: string | null;
  commit?: string | null;
  /** Uncommitted changes in a local folder. */
  dirty?: boolean | null;
  framework?: string | null;
  /** A server agent: its repository (no credentials) and branches. */
  repo?: string | null;
  default_branch?: string | null;
  branches?: string[];
}

export interface AutomationAgent {
  name: string;
  last_seen_at: string;
  online: boolean;
  options: AgentOption[];
  info: AgentInfo;
}


// --- Automated tests' catalog (synced into cases after a preview) ---

export type CatalogAction = "create" | "update" | "link" | "unchanged" | "outdated";

export interface CatalogSuggestion {
  case_id: number;
  key: string;
  title: string;
  path: string;
  /** 0..1, how alike the titles read. */
  score: number;
}

export interface CatalogItem {
  action: CatalogAction;
  /** The test's key; becomes the case's automation key. */
  key: string;
  title: string;
  path: string[];
  case_id: number | null;
  case_key: string | null;
  case_title: string | null;
  changes: string[];
  note: string | null;
  suggestions: CatalogSuggestion[];
}

export interface CatalogPreview {
  agent: string | null;
  uploaded_at: string;
  suite: string;
  counts: Record<CatalogAction, number>;
  items: CatalogItem[];
}

export interface CatalogApplied {
  created: number;
  updated: number;
  linked: number;
  outdated: number;
  skipped: number;
}
