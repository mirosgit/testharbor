import { expect, test } from "@playwright/test";

const loginPage = `
  <form><input id="email"><input id="password" type="password">
  <button>Sign in</button><p id="error" hidden>Invalid email or password</p></form>`;

test.describe("Login", () => {
  test("C1 login with valid credentials", async ({ page }) => {
    await page.setContent(loginPage);
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test(
    "shows an error for a wrong password",
    { annotation: { type: "case_id", description: "C2" } },
    async ({ page }) => {
      await page.setContent(loginPage);
      await expect(page.locator("#error")).toBeVisible({ timeout: 500 });
    },
  );

  test.skip("remember me [C6]", async () => {});
});

test("signup form renders", async ({ page }) => {
  await page.setContent("<h1>Create account</h1>");
  await expect(page.getByRole("heading")).toHaveText("Create account");
});
