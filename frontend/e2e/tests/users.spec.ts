import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("admin invites a tester who sets a password; testers can't manage users", async ({ page, browser }) => {
  await login(page);
  const email = `e2e-tester-${Date.now().toString(36)}@example.com`;

  await page.goto("/settings/users");
  await page.getByRole("button", { name: "Invite user" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Create link" }).click();
  const url = await page.getByTestId("invite-url").inputValue();
  expect(url).toContain("/invite/inv_");
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByTestId("invites")).toContainText(email);

  // The tester opens the link in their own browser.
  const ctx = await browser.newContext();
  const tp = await ctx.newPage();
  await tp.goto(url);
  await expect(tp.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await tp.getByLabel("Your name").fill("Tess Tester");
  await tp.getByLabel("Password", { exact: true }).fill("tester passphrase 1");
  await tp.getByLabel("Repeat password").fill("tester passphrase 1");
  await tp.getByRole("button", { name: "Create account" }).click();
  await expect(tp.getByRole("heading", { name: "Projects" })).toBeVisible();

  // Testers don't get user management.
  await tp.getByRole("button", { name: "Account menu" }).click();
  await expect(tp.getByRole("menuitem", { name: "Profile" })).toBeVisible();
  await expect(tp.getByRole("menuitem", { name: "Users" })).toHaveCount(0);
  await tp.keyboard.press("Escape");
  expect((await tp.request.get("/api/users")).status()).toBe(403);

  // The link was one-time.
  await tp.goto(url);
  await expect(tp.getByText("This link is invalid or has expired.")).toBeVisible();

  // Deactivation signs the tester out immediately.
  await page.reload();
  const row = page.getByTestId("users").locator("> div").filter({ hasText: email });
  await row.getByRole("button", { name: "Actions for Tess Tester" }).click();
  await page.getByRole("menuitem", { name: "Deactivate" }).click();
  await page.getByRole("button", { name: "Deactivate" }).click();
  await expect(row).toContainText("deactivated");
  await tp.goto("/");
  await expect(tp).toHaveURL(/\/login/);
  expect((await tp.request.get("/api/projects")).status()).toBe(401);
  await ctx.close();

  // Deleted for good.
  await row.getByRole("button", { name: "Actions for Tess Tester" }).click();
  await page.getByRole("menuitem", { name: "Delete…" }).click();
  await page.getByRole("button", { name: "Delete user" }).click();
  await expect(page.getByTestId("users")).not.toContainText(email);
});
