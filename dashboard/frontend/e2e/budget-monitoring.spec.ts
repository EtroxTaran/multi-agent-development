/**
 * Journey 7: Budget Monitoring & Alerts (P2)
 * Tests for viewing and monitoring budget usage
 */

import { test, expect } from "@playwright/test";
import { ProjectDashboardPage } from "./page-objects";
import { setupApiMocks, mockProjects, mockBudget } from "./fixtures";

test.describe("Budget Monitoring", () => {
  test("should display budget overview", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      budget: mockBudget.normal,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("budget");

    // Check budget info is visible
    await expect(page.getByText(/spent|total/i)).toBeVisible();
    await expect(page.getByText(/\$1\.25/)).toBeVisible();
  });

  test("should show budget progress bar", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      budget: mockBudget.normal,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("budget");

    // Should show percentage used
    await expect(page.getByText(/12\.5%|percent/i)).toBeVisible();
  });

  test("should show near-limit warning", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      budget: mockBudget.nearLimit,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("budget");

    // Should show high usage percentage
    await expect(page.getByText(/95%|percent/i)).toBeVisible();
  });

  test("should show disabled budget state", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      budget: mockBudget.disabled,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("budget");

    // Should show disabled or $0 state
    await expect(
      page
        .locator('[role="tabpanel"]')
        .filter({ hasText: /\$0|disabled|not enabled/i }),
    ).toBeVisible();
  });
});
