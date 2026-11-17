import { expect, test } from "@playwright/test";

import { ADMIN, unique } from "./helpers";

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

  await page.getByRole("button", { name: "Add case" }).first().click();
  await page.getByLabel("Title").fill("Pay with a saved card");
  await page.getByRole("button", { name: "Add step" }).click();
  await page.getByLabel("Step 1 action").fill("Choose the saved card and pay");
  await page.getByLabel("Step 1 expected result").fill("Order confirmation is shown");
  await page.getByRole("button", { name: "Create case" }).click();

  const sheet = page.getByTestId("case-sheet");
  await expect(sheet.getByRole("heading", { name: "Pay with a saved card" })).toBeVisible();
  await expect(sheet.getByText("Order confirmation is shown")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden(); // focus is trapped in the sheet until it has closed

  const row = page.getByTestId("case-row").filter({ hasText: "Pay with a saved card" });
  await expect(row).toBeVisible();

  // Search narrows the list.
  await page.getByLabel("Search cases").fill("nothing like this");
  await expect(page.getByLabel("Search cases")).toHaveValue("nothing like this");
  await expect(page.getByText("No cases match the filters.")).toBeVisible();
});
