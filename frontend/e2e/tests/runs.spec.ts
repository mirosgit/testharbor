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

test("Playwright JSON upload links each case to its test in the HTML report", async ({ page }) => {
  await login(page);
  const { project, cases } = await seedProject(page.request, ["Checkout works"]);
  const report = {
    config: { projects: [{ name: "chromium" }] },
    suites: [{ title: "checkout.spec.ts", specs: [{
      title: `${cases[0].key} checkout works`, id: "abc123-def456", file: "checkout.spec.ts", tags: [],
      tests: [{ status: "expected", projectName: "chromium", annotations: [], results: [{ status: "passed", duration: 1200 }] }],
    }] }],
  };
  const reportUrl = "http://127.0.0.1:8766/lbrjgd/index.html";
  const r = await page.request.post(
    `/api/projects/${project.id}/runs/import-junit?run_name=PW%20json&report_url=${encodeURIComponent(reportUrl)}`,
    { multipart: { file: { name: "results.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) } } },
  );
  expect(r.ok(), await r.text()).toBeTruthy();

  await page.goto(`/projects/${project.id}/runs/${(await r.json()).run_id}`);
  await expect(page.getByRole("link", { name: "Report", exact: true })).toHaveAttribute("href", reportUrl);
  const row = page.getByTestId("run-case-row").filter({ hasText: "checkout works" });
  await expect(row.getByRole("link", { name: `Open ${cases[0].key} in the report` })).toHaveAttribute(
    "href",
    `${reportUrl}#?testId=abc123-def456`,
  );
});

test("Run autotests: an agent picks the job up and results land in the run", async ({ page }) => {
  await login(page);
  const { project, cases } = await seedProject(page.request, ["Pay by card", "Pay by invoice"]);
  await page.goto(`/projects/${project.id}/runs`);
  await page.getByRole("button", { name: "Run autotests" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByTestId("agent-status")).toContainText("No agent is online");
  await dialog.getByRole("button", { name: "Run", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/\d+$/);
  const runId = Number(page.url().split("/").pop());
  await expect(page.getByTestId("autotests-status")).toHaveText("Autotests: Waiting for an agent");

  // What `testcli agent` does: claim, stream output, upload the report into the run, finish.
  const claim = await page.request.post(`/api/projects/${project.id}/automation/claim`, { data: { agent: "e2e-box" } });
  const job = await claim.json();
  expect(job.run_id).toBe(runId);
  await page.request.post(`/api/automation/jobs/${job.id}/progress`, { data: { log: "Running 2 tests using 1 worker\n" } });
  await expect(page.getByTestId("autotests-status")).toHaveText("Autotests: Running");
  await expect(page.getByTestId("autotests-log")).toContainText("Running 2 tests");

  const report = {
    suites: [{ title: "pay.spec.ts", specs: cases.map((c, i) => ({
      title: `${c.key} pays`, id: `id-${i}`, file: "pay.spec.ts", tags: [],
      tests: [{ status: i ? "unexpected" : "expected", annotations: [],
        results: [{ status: i ? "failed" : "passed", duration: 900, errors: i ? [{ message: "Invoice not sent" }] : [] }] }],
    })) }],
  };
  await page.request.post(`/api/projects/${project.id}/runs/import-junit?run_id=${runId}`, {
    multipart: { file: { name: "results.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(report)) } },
  });
  await page.request.post(`/api/automation/jobs/${job.id}/finish`, {
    data: { status: "finished", exit_code: 1, message: "2 tests (1 failed, 1 passed)", log: "1 failed\n" },
  });

  await expect(page.getByTestId("autotests-status")).toHaveText("Autotests: Finished");
  await expect(page.getByTestId("run-case-row").filter({ hasText: cases[1].key })).toContainText("Invoice not sent");

  // Re-run only what failed, into the same run.
  await page.getByRole("button", { name: "Run autotests" }).click();
  await page.getByRole("dialog").getByText("Failed cases").click();
  await page.getByRole("dialog").getByRole("button", { name: "Run", exact: true }).click();
  await expect(page.getByTestId("autotests-status")).toHaveText("Autotests: Waiting for an agent");
  await expect(page.getByTestId("autotests-panel")).toContainText("1 cases");
  await page.getByTestId("autotests-panel").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("autotests-status")).toHaveText("Autotests: Cancelled");
});
