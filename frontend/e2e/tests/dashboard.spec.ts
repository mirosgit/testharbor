import { expect, test } from "@playwright/test";

import { login, seedProject } from "./helpers";

test("dashboard: coverage, review queue and results, with links to the cases", async ({ page }) => {
  await login(page);
  const { project, suite, section, cases } = await seedProject(page.request, ["Pay by card", "Refund an order"]);
  const api = page.request;
  expect((await api.patch(`/api/cases/${cases[0].id}`, { data: { automation_status: "automated" } })).ok()).toBeTruthy();
  const review = await api.post("/api/cases", {
    data: { section_id: section.id, title: "Export orders", state: "pending_review", automation_status: "automated" },
  });
  expect(review.ok()).toBeTruthy();
  const run = await (await api.post(`/api/projects/${project.id}/runs`, { data: { name: "Smoke", suite_id: suite.id } })).json();
  for (const [c, status] of [[cases[0], "passed"], [cases[1], "failed"]] as const) {
    expect((await api.post(`/api/runs/${run.id}/results`, { data: { case_id: c.id, status } })).ok()).toBeTruthy();
  }

  await page.goto(`/projects/${project.id}`);
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByTestId("dash-coverage")).toContainText("66.7%"); // 2 of 3 automated
  await expect(page.getByTestId("dash-coverage")).toContainText("2 of 3 cases");
  await expect(page.getByTestId("dash-pass-rate")).toContainText("50%");
  await expect(page.getByTestId("dash-failing")).toContainText("Refund an order");

  await page.getByRole("radio", { name: "7 days" }).click();
  await expect(page).toHaveURL(/days=7/);
  await expect(page.getByTestId("dash-pass-rate")).toContainText("50%");

  // The review tile opens the list filtered to the cases waiting.
  await expect(page.getByTestId("dash-review")).toContainText("1");
  await page.getByTestId("dash-review").getByRole("link", { name: "Review cases" }).click();
  await expect(page.getByTestId("case-row")).toHaveCount(1);
  await expect(page.getByTestId("case-row")).toContainText("Export orders");
});
