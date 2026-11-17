import { readFileSync } from "node:fs";
import path from "node:path";

import { expect, request, test } from "@playwright/test";

import { login, seedProject } from "./helpers";

test("manual run: create from a suite and record results", async ({ page }) => {
  await login(page);
  const { project, suite } = await seedProject(page.request, ["Login works", "Logout works"]);

  await page.goto(`/projects/${project.id}/cases?suite=${suite.id}`);
  await expect(page.getByTestId("case-row")).toHaveCount(2);
  await page.getByRole("button", { name: "Create run" }).click();
  await page.getByLabel("Name").fill("Release smoke");
  await page.getByRole("button", { name: "Create run" }).last().click();

  await expect(page.getByRole("heading", { name: "Release smoke" })).toBeVisible();
  await expect(page.getByText("executed (0/2)")).toBeVisible();

  // Execute the first case from the side panel.
  await page.getByTestId("run-case-row").filter({ hasText: "Login works" }).getByText("Login works").click();
  const sheet = page.getByTestId("execute-sheet");
  await sheet.getByRole("radio", { name: "Failed" }).click();
  await sheet.getByLabel("Comment").fill("Button is hidden on small screens");
  await sheet.getByRole("button", { name: "Add result" }).click();
  await expect(sheet.getByTestId("run-results")).toContainText("Button is hidden on small screens");
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();

  // Quick status from the row menu.
  await page.getByTestId("run-case-row").filter({ hasText: "Logout works" }).getByRole("button", { name: /Status:/ }).click();
  await page.getByRole("menuitem", { name: "Passed" }).click();

  await expect(page.getByText("executed (2/2)")).toBeVisible();
  await expect(page.getByText("50%", { exact: true })).toBeVisible(); // pass rate

  // The case shows the run in its history.
  await page.goto(`/projects/${project.id}/cases?suite=${suite.id}`);
  await page.getByTestId("case-row").filter({ hasText: "Login works" }).getByText("Login works").click();
  await expect(page.getByTestId("case-history")).toContainText("Release smoke");
});

test("JUnit upload with an API token creates a CI run", async ({ page, baseURL }) => {
  await login(page);
  const { project, cases } = await seedProject(page.request, ["Login works"]);
  const token = (await (await page.request.post("/api/tokens", { data: { name: "e2e" } })).json()).token;

  const caseKey = cases[0].key;
  const xml = readFileSync(path.join(__dirname, "fixtures", "sample.xml"), "utf8").replaceAll("C_ID", caseKey);
  const bot = await request.newContext({ baseURL, extraHTTPHeaders: { Authorization: `Bearer ${token}` } });
  const r = await bot.post(`/api/projects/${project.id}/runs/import-junit?run_name=Nightly%20e2e&branch=main&auto_create=true`, {
    multipart: { file: { name: "junit.xml", mimeType: "application/xml", buffer: Buffer.from(xml) } },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
  const body = await r.json();
  expect(body).toMatchObject({ total: 2, matched: 1, created: 1, unmatched: [] });
  await bot.dispose();

  await page.goto(`/projects/${project.id}/runs`);
  const runRow = page.getByTestId("runs-list").getByRole("link", { name: "Nightly e2e" });
  await expect(runRow).toBeVisible();
  await runRow.click();
  await expect(page.getByText("main", { exact: true })).toBeVisible();
  await expect(page.getByTestId("run-case-row").filter({ hasText: "Login works" })).toContainText("expected 200, got 500");
});
