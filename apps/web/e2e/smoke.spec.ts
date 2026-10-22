/**
 * Smoke: the landing page loads without a script error, and signing in with a
 * seeded demo role reaches the signed-in app. The two paths a demo fails on
 * first, run against the real API rather than a mock (T-15).
 */
import { expect, test } from "@playwright/test";

test("the landing page loads without a script error", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (err) => errors.push(err.message));
  await page.goto("/");
  await expect(page).toHaveTitle(/AegisAI/);
  await expect(page.getByRole("heading").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("signing in as a demo analyst reaches the app", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "analyst analyst@aegis.local", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});
