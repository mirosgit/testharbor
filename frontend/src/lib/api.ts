import type {
  AutomationAgent,
  AutomationJob,
  AutomationJobDetail,
  CatalogApplied,
  CatalogPreview,
  RunParams,
  CaseBulkUpdate,
  CaseSort,
  CaseValues,
  FieldValues,
  RunSort,
  ImportTarget,
  AdminUser,
  Invite,
  InviteInfo,
  InviteLink,
  Me,
  Role,
  ApiToken,
  JUnitImportResult,
  CaseFilter,
  CaseHistoryItem,
  ResultInput,
  RunCase,
  RunList,
  RunSelection,
  TestResult,
  TestRun,
  CaseInput,
  CaseList,
  ImportResult,
  Project,
  Section,
  Suite,
  TestCase,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function detailMessage(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0]?.msg) return `${d[0].loc?.slice(1).join(".") ?? ""}: ${d[0].msg}`;
  }
  return fallback;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("content-type", "application/json");
  const res = await fetch(path, { ...init, headers, credentials: "same-origin" });
  const publicCall = path.startsWith("/api/auth/login") || path.startsWith("/api/invites/accept/");
  if (res.status === 401 && typeof window !== "undefined" && !publicCall) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/login?next=${next}`;
    throw new ApiError(401, "Not authenticated");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, detailMessage(body, `${res.status} ${res.statusText}`));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

export function filterParams(f: object): URLSearchParams {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (k === "fields" && v && typeof v === "object" && !Array.isArray(v)) {
      for (const [name, values] of Object.entries(v as Record<string, string[]>))
        values.forEach((value) => p.append("field", `${name}=${value}`));
      continue;
    }
    if (k === "columns" && Array.isArray(v)) {
      if (v.length === 0) p.append("columns", ""); // explicit "none"
      v.forEach((c) => p.append("columns", String(c)));
      continue;
    }
    if (v === undefined || v === null || v === "") continue;
    if (k === "roles" && Array.isArray(v)) {
      v.forEach((x) => p.append("role", String(x))); // the query param is singular
      continue;
    }
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)));
    else p.set(k, String(v));
  }
  return p;
}

export interface Paging {
  limit: number;
  offset?: number;
  order?: "asc" | "desc";
}

export const api = {
  startAutotests: (
    projectId: number,
    body: {
      run_id?: number;
      name?: string;
      case_ids?: number[];
      only_failed?: boolean;
      params?: RunParams;
      agent?: string;
      branch?: string;
    },
  ) => request<AutomationJob>(`/api/projects/${projectId}/automation/jobs`, json("POST", body)),
  autotestJobs: (projectId: number, runId?: number) =>
    request<AutomationJob[]>(
      `/api/projects/${projectId}/automation/jobs?${filterParams({ run_id: runId, limit: 10 })}`,
    ),
  autotestJob: (id: number) => request<AutomationJobDetail>(`/api/automation/jobs/${id}`),
  cancelAutotests: (id: number) => request<AutomationJob>(`/api/automation/jobs/${id}/cancel`, json("POST")),
  agents: (projectId: number) => request<AutomationAgent[]>(`/api/projects/${projectId}/automation/agents`),
  catalog: (projectId: number) => request<CatalogPreview>(`/api/projects/${projectId}/automation/catalog`),
  applyCatalog: (projectId: number, body: { uploaded_at: string; links: Record<string, number>; skip: string[] }) =>
    request<CatalogApplied>(`/api/projects/${projectId}/automation/catalog/apply`, json("POST", body)),

  setupStatus: () => request<{ has_users: boolean }>("/api/auth/setup-status"),
  login: (email: string, password: string) =>
    request<Me>("/api/auth/login", json("POST", { email, password })),
  logout: () => request<void>("/api/auth/logout", json("POST")),
  me: () => request<Me>("/api/auth/me"),
  updateProfile: (name: string) => request<Me>("/api/auth/me", json("PATCH", { name })),
  changePassword: (current_password: string, new_password: string) =>
    request<Me>("/api/auth/password", json("POST", { current_password, new_password })),
  logoutOthers: () => request<Me>("/api/auth/logout-others", json("POST")),

  users: () => request<AdminUser[]>("/api/users"),
  updateUser: (id: number, body: { role?: Role; is_active?: boolean; unlock?: boolean; name?: string }) =>
    request<AdminUser>(`/api/users/${id}`, json("PATCH", body)),
  resetLink: (id: number) => request<InviteLink>(`/api/users/${id}/reset-link`, json("POST")),
  invites: () => request<Invite[]>("/api/invites"),
  createInvite: (email: string, role: Role) =>
    request<InviteLink>("/api/invites", json("POST", { email, role })),
  revokeInvite: (id: number) => request<void>(`/api/invites/${id}`, json("DELETE")),
  inviteInfo: (token: string) => request<InviteInfo>(`/api/invites/accept/${encodeURIComponent(token)}`),
  acceptInvite: (token: string, body: { name?: string; password: string }) =>
    request<Me>(`/api/invites/accept/${encodeURIComponent(token)}`, json("POST", body)),

  projects: () => request<Project[]>("/api/projects"),
  project: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (body: { name: string; description?: string }) =>
    request<Project>("/api/projects", json("POST", body)),
  updateProject: (id: number, body: { name?: string; description?: string; roles?: string[] }) =>
    request<Project>(`/api/projects/${id}`, json("PATCH", body)),
  renameRole: (id: number, old: string, name: string) =>
    request<Project>(`/api/projects/${id}/roles/rename`, json("POST", { old, new: name })),
  deleteProject: (id: number) => request<void>(`/api/projects/${id}`, json("DELETE")),

  suites: (projectId: number) => request<Suite[]>(`/api/projects/${projectId}/suites`),
  createSuite: (projectId: number, body: { name: string; description?: string }) =>
    request<Suite>(`/api/projects/${projectId}/suites`, json("POST", body)),
  updateSuite: (id: number, body: { name?: string; description?: string }) =>
    request<Suite>(`/api/suites/${id}`, json("PATCH", body)),
  deleteSuite: (id: number) => request<void>(`/api/suites/${id}`, json("DELETE")),

  sections: (suiteId: number) => request<Section[]>(`/api/suites/${suiteId}/sections`),
  createSection: (suiteId: number, body: { name: string; parent_id?: number | null }) =>
    request<Section>(`/api/suites/${suiteId}/sections`, json("POST", body)),
  updateSection: (
    id: number,
    body: { name?: string; parent_id?: number | null; position?: number },
  ) => request<Section>(`/api/sections/${id}`, json("PATCH", body)),
  deleteSection: (id: number) => request<void>(`/api/sections/${id}`, json("DELETE")),

  cases: (projectId: number, f: CaseFilter, page: Paging & { sort?: CaseSort } = { limit: 5000 }) =>
    request<CaseList>(`/api/projects/${projectId}/cases?${filterParams({ ...f, ...page })}`),
  tags: (projectId: number) => request<string[]>(`/api/projects/${projectId}/tags`),
  customFields: (projectId: number) => request<FieldValues[]>(`/api/projects/${projectId}/custom-fields`),
  caseValues: (projectId: number) => request<CaseValues>(`/api/projects/${projectId}/case-values`),
  case: (ref: number | string) => request<TestCase>(`/api/cases/${ref}`),
  createCase: (body: CaseInput) => request<TestCase>("/api/cases", json("POST", body)),
  updateCase: (id: number, body: Partial<CaseInput>) =>
    request<TestCase>(`/api/cases/${id}`, json("PATCH", body)),
  bulkUpdateCases: (body: CaseBulkUpdate) =>
    request<{ updated: number }>("/api/cases/bulk-update", json("POST", body)),
  deleteCase: (id: number) => request<void>(`/api/cases/${id}`, json("DELETE")),
  moveCases: (caseIds: number[], sectionId: number, position?: number) =>
    request<TestCase[]>(
      "/api/cases/move",
      json("POST", { case_ids: caseIds, section_id: sectionId, position }),
    ),

  importCases: (suiteId: number, file: File, target: ImportTarget) => {
    const fd = new FormData();
    fd.append("file", file);
    const q = filterParams({ ...target, keep_paths: String(target.keep_paths), dry_run: target.dry_run ? "true" : undefined });
    return request<ImportResult>(`/api/suites/${suiteId}/import?${q}`, { method: "POST", body: fd });
  },
  exportUrl: (suiteId: number, format: "csv" | "json") =>
    `/api/suites/${suiteId}/export?format=${format}`,

  runs: (projectId: number, params: { closed?: boolean; sort?: RunSort } & Partial<Paging> = {}) =>
    request<RunList>(`/api/projects/${projectId}/runs?${filterParams(params)}`),
  run: (id: number) => request<TestRun>(`/api/runs/${id}`),
  createRun: (projectId: number, body: RunSelection & { name: string; description?: string }) =>
    request<TestRun>(`/api/projects/${projectId}/runs`, json("POST", body)),
  updateRun: (id: number, body: { name?: string; description?: string; closed?: boolean; report_url?: string | null }) =>
    request<TestRun>(`/api/runs/${id}`, json("PATCH", body)),
  deleteRun: (id: number) => request<void>(`/api/runs/${id}`, json("DELETE")),
  runCases: (id: number) => request<RunCase[]>(`/api/runs/${id}/cases`),
  addRunCases: (id: number, sel: RunSelection) =>
    request<TestRun>(`/api/runs/${id}/cases`, json("POST", sel)),
  removeRunCase: (id: number, caseId: number) =>
    request<void>(`/api/runs/${id}/cases/${caseId}`, json("DELETE")),
  addResult: (runId: number, body: ResultInput) =>
    request<TestResult>(`/api/runs/${runId}/results`, json("POST", body)),
  addResults: (runId: number, results: ResultInput[]) =>
    request<TestResult[]>(`/api/runs/${runId}/results/bulk`, json("POST", { results })),
  caseResultsInRun: (runId: number, caseId: number) =>
    request<TestResult[]>(`/api/runs/${runId}/cases/${caseId}/results`),
  caseHistory: (caseId: number) => request<CaseHistoryItem[]>(`/api/cases/${caseId}/history`),

  tokens: () => request<ApiToken[]>("/api/tokens"),
  createToken: (name: string) =>
    request<ApiToken & { token: string }>("/api/tokens", json("POST", { name })),
  revokeToken: (id: number) => request<void>(`/api/tokens/${id}`, json("DELETE")),
  importJunit: (
    projectId: number,
    files: File[],
    params: { run_name?: string; branch?: string; commit?: string; auto_create?: boolean },
  ) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("file", f));
    const q = filterParams({ ...params, auto_create: params.auto_create ? "true" : undefined });
    return request<JUnitImportResult>(`/api/projects/${projectId}/runs/import-junit?${q}`, {
      method: "POST",
      body: fd,
    });
  },
};
