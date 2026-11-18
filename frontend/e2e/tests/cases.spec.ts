import { expect, test } from "@playwright/test";

import { ADMIN, login, seedProject, unique } from "./helpers";

test("log in, create a project, suite, section and case", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(ADMIN.email);
  await page.getByLabel("Password").fill(ADMIN.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();

  const name = unique("Smoke project");
  await page.getByRole("button", { name: "New project" }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByRole("link", { name }).click();

  await page.getByRole("button", { name: "Create a suite" }).click();
  await page.getByLabel("Name").fill("Web app");
  await page.getByRole("button", { name: "Create", exact: true }).click();

  await page.getByRole("button", { name: "Create a section" }).click();
  await page.getByLabel("Name").fill("Checkout");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("tree").getByText("Checkout")).toBeVisible();

  // Project roles are set up once in the project settings.
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByLabel("New role").fill("Admin, Cashier");
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByTestId("project-roles").getByRole("listitem")).toHaveText(["Admin", "Cashier"]);
  await page.getByRole("link", { name: "Test cases" }).click();

  await page.getByRole("button", { name: "Add case" }).first().click();
  await page.getByLabel("Title").fill("Pay with a saved card");
  await page.getByRole("button", { name: "Add step" }).click();
  await page.getByLabel("Step 1 action").fill("Choose the saved card and pay");
  await page.getByLabel("Step 1 expected result").fill("Order confirmation is shown");
  await page.getByRole("combobox", { name: "State" }).click();
  await page.getByRole("option", { name: "Draft" }).click();
  // Pickers: search, choose with the mouse or create with Enter.
  await page.getByRole("combobox", { name: "Owner" }).click();
  await page.keyboard.type("Jane QA");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("combobox", { name: "Owner" })).toHaveText("Jane QA");
  await page.getByRole("combobox", { name: "Sprint" }).click();
  await page.keyboard.type("Sprint 7");
  await page.keyboard.press("Enter");
  await page.getByRole("combobox", { name: "Applicable Roles" }).click();
  await page.getByRole("option", { name: "Admin" }).click();
  await page.getByRole("option", { name: "Cashier" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("combobox", { name: "Applicable Roles" })).toContainText("AdminCashier");
  await page.getByRole("combobox", { name: "Tags" }).click();
  await page.keyboard.type("Payments");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Add field" }).click();
  await page.getByRole("combobox", { name: "Field 1 name" }).click();
  await page.keyboard.type("Reviewer");
  await page.keyboard.press("Enter");
  await page.getByLabel("Field 1 value").fill("Ann");
  await page.getByRole("button", { name: "Create case" }).click();

  const sheet = page.getByTestId("case-sheet");
  await expect(sheet.getByRole("heading", { name: "Pay with a saved card" })).toBeVisible();
  await expect(sheet.getByText("Order confirmation is shown")).toBeVisible();
  const meta = sheet.getByTestId("case-meta");
  await expect(meta).toContainText("Draft");
  await expect(meta).toContainText("Jane QA");
  await expect(meta).toContainText("Sprint 7");
  await expect(meta).toContainText("AdminCashier");
  await expect(meta).toContainText("by E2E Admin");
  await expect(sheet.getByTestId("custom-fields")).toContainText("ReviewerAnn");
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden(); // focus is trapped in the sheet until it has closed

  const row = page.getByTestId("case-row").filter({ hasText: "Pay with a saved card" });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Draft"); // non-active states are flagged in the list

  // Filter by a built-in field from the "Fields" popover.
  await page.getByRole("button", { name: "Fields" }).click();
  await page.getByRole("combobox", { name: "Field" }).click();
  await page.getByRole("option", { name: "Applicable Roles" }).click();
  await page.getByRole("checkbox", { name: "Cashier" }).click();
  await page.keyboard.press("Escape");
  await expect(row).toBeVisible();
  await page.getByRole("button", { name: "Clear", exact: true }).click();

  // Bulk edit the selected cases.
  await row.getByRole("checkbox").click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const bulk = page.getByRole("dialog");
  await bulk.getByRole("combobox", { name: "State" }).click();
  await page.getByRole("option", { name: "Outdated" }).click();
  await bulk.getByRole("button", { name: "Apply to 1 cases" }).click();
  await expect(bulk).toBeHidden();
  await expect(row).toContainText("Outdated");

  // Search narrows the list.
  await page.getByLabel("Search cases").fill("nothing like this");
  await expect(page.getByLabel("Search cases")).toHaveValue("nothing like this");
  await expect(page.getByText("No cases match the filters.")).toBeVisible();
});

test("sort and paginate the case list", async ({ page }) => {
  await login(page);
  const titles = Array.from({ length: 55 }, (_, i) => `Case ${String(i + 1).padStart(2, "0")}`);
  const { project } = await seedProject(page.request, titles);
  await page.goto(`/projects/${project.id}/cases`);
  const rows = page.getByTestId("case-row");
  await expect(rows.first()).toContainText("Case 01");

  // 50 per page: page 2 has the remaining 5.
  await page.getByLabel("Per page").selectOption("50");
  await expect(page.getByTestId("pager")).toContainText("1–50 of 55");
  await expect(rows).toHaveCount(50);
  await page.getByRole("button", { name: "Next page" }).click();
  await expect(page.getByTestId("pager")).toContainText("51–55 of 55");
  await expect(rows).toHaveCount(5);

  // Sorting by title descending starts again from page 1.
  await page.getByRole("button", { name: /^Sort:/ }).click();
  await page.getByRole("menuitem", { name: "Title" }).click();
  await page.getByRole("button", { name: /^Sort:/ }).click();
  await page.getByRole("menuitem", { name: "Descending" }).click();
  await expect(page.getByTestId("pager")).toContainText("1–50 of 55");
  await expect(rows.first()).toContainText("Case 55");
  await page.getByLabel("Per page").selectOption("100");
});
