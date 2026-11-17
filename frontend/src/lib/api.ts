import type {
  CaseFilter,
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
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/login")) {
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

export function filterParams(f: CaseFilter): URLSearchParams {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, String(x)));
    else p.set(k, String(v));
  }
  return p;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ principal: string }>("/api/auth/login", json("POST", { username, password })),
  logout: () => request<void>("/api/auth/logout", json("POST")),
  me: () => request<{ principal: string }>("/api/auth/me"),

  projects: () => request<Project[]>("/api/projects"),
  project: (id: number) => request<Project>(`/api/projects/${id}`),
  createProject: (body: { name: string; description?: string }) =>
    request<Project>("/api/projects", json("POST", body)),
  updateProject: (id: number, body: { name?: string; description?: string }) =>
    request<Project>(`/api/projects/${id}`, json("PATCH", body)),
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

  cases: (projectId: number, f: CaseFilter) =>
    request<CaseList>(`/api/projects/${projectId}/cases?${filterParams({ ...f })}&limit=5000`),
  tags: (projectId: number) => request<string[]>(`/api/projects/${projectId}/tags`),
  case: (ref: number | string) => request<TestCase>(`/api/cases/${ref}`),
  createCase: (body: CaseInput) => request<TestCase>("/api/cases", json("POST", body)),
  updateCase: (id: number, body: Partial<CaseInput>) =>
    request<TestCase>(`/api/cases/${id}`, json("PATCH", body)),
  deleteCase: (id: number) => request<void>(`/api/cases/${id}`, json("DELETE")),
  moveCases: (caseIds: number[], sectionId: number, position?: number) =>
    request<TestCase[]>(
      "/api/cases/move",
      json("POST", { case_ids: caseIds, section_id: sectionId, position }),
    ),

  importCases: (suiteId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<ImportResult>(`/api/suites/${suiteId}/import`, { method: "POST", body: fd });
  },
  exportUrl: (suiteId: number, format: "csv" | "json") =>
    `/api/suites/${suiteId}/export?format=${format}`,
};
