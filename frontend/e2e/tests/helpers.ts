import { expect, type APIRequestContext, type Page } from "@playwright/test";

// Created/updated with a random password by `make e2e` (see Makefile).
export const ADMIN = {
  email: process.env.E2E_EMAIL ?? "e2e-admin@testharbor.local",
  password: process.env.E2E_PASSWORD ?? "",
};

export const unique = (prefix: string) => `${prefix} ${Date.now().toString(36)}`;

/** Log in through the API; the cookie is shared with the page's browser context. */
export async function login(page: Page) {
  const r = await page.request.post("/api/auth/login", { data: ADMIN });
  expect(r.ok()).toBeTruthy();
}

async function post<T>(api: APIRequestContext, url: string, data: unknown): Promise<T> {
  const r = await api.post(url, { data });
  expect(r.ok(), `${url}: ${r.status()} ${await r.text()}`).toBeTruthy();
  return (await r.json()) as T;
}

/** Create project › suite › section › cases through the API. */
export async function seedProject(api: APIRequestContext, caseTitles: string[]) {
  const project = await post<{ id: number; name: string }>(api, "/api/projects", { name: unique("E2E") });
  const suite = await post<{ id: number }>(api, `/api/projects/${project.id}/suites`, { name: "Web" });
  const section = await post<{ id: number }>(api, `/api/suites/${suite.id}/sections`, { name: "Login" });
  const cases = [];
  for (const title of caseTitles) {
    cases.push(
      await post<{ id: number; key: string }>(api, "/api/cases", {
        section_id: section.id,
        title,
        steps: [{ action: "Open the app", expected: "It loads" }],
      }),
    );
  }
  return { project, suite, section, cases };
}
