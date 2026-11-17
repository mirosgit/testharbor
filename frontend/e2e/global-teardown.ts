import { request, type FullConfig } from "@playwright/test";

import { ADMIN } from "./tests/helpers";

/** Remove what the smoke tests created, so they can run against a dev instance. */
export default async function globalTeardown(config: FullConfig) {
  const api = await request.newContext({ baseURL: config.projects[0].use.baseURL });
  try {
    if (!(await api.post("/api/auth/login", { data: ADMIN })).ok()) return;
    const projects: { id: number; name: string }[] = await (await api.get("/api/projects")).json();
    for (const p of projects.filter((p) => /^(E2E|Smoke project) [0-9a-z]+$/.test(p.name))) {
      await api.delete(`/api/projects/${p.id}`);
    }
    const tokens: { id: number; name: string; revoked_at: string | null }[] = await (await api.get("/api/tokens")).json();
    for (const t of tokens.filter((t) => t.name === "e2e" && !t.revoked_at)) {
      await api.delete(`/api/tokens/${t.id}`);
    }
    // Users can't be deleted (history is kept); deactivate the ones the tests invited.
    const users: { id: number; email: string; is_active: boolean }[] = await (await api.get("/api/users")).json();
    for (const u of users.filter((u) => /^e2e-tester-[0-9a-z]+@example\.com$/.test(u.email) && u.is_active)) {
      await api.patch(`/api/users/${u.id}`, { data: { is_active: false } });
    }
  } finally {
    await api.dispose();
  }
}
