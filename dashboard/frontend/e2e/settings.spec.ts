/**
 * Journey 10: Settings Display (P3)
 * Tests for settings page functionality
 */

import { test, expect } from "@playwright/test";
import { setupApiMocks, mockProjects } from "./fixtures";

test.describe("Settings Display", () => {
  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.single });
  });

  test("should navigate to settings page", async ({ page }) => {
    await page.goto("/");

    // Find and click settings link (usually in navigation)
    const settingsLink = page.getByRole("link", { name: /settings/i });

    if (await settingsLink.isVisible()) {
      await settingsLink.click();
      await expect(page).toHaveURL(/settings/);
    } else {
      // Settings might be accessed via direct URL
      await page.goto("/settings");
      await expect(page.getByText(/settings|configuration/i)).toBeVisible();
    }
  });

  test("should display settings sections", async ({ page }) => {
    await page.goto("/settings");

    // Should show settings content
    await expect(
      page.getByText(/settings|configuration|preferences/i).first(),
    ).toBeVisible();
  });

  test("should show API configuration", async ({ page }) => {
    await page.goto("/settings");

    // Should show API or connection settings
    await expect(
      page.getByText(/api|server|connection|url/i).first(),
    ).toBeVisible();
  });
});
