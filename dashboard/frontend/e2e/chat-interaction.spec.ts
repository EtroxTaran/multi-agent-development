/**
 * Journey 9: Chat Interaction (P3)
 * Tests for chat functionality and HITL interaction
 */

import { test, expect } from "@playwright/test";
import { ProjectDashboardPage } from "./page-objects";
import { setupApiMocks, mockProjects, mockWorkflowStatus } from "./fixtures";

test.describe("Chat Interaction", () => {
  test("should display chat panel", async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.single });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("chat");

    // Should show chat input
    await expect(page.locator("textarea")).toBeVisible();
  });

  test("should show HITL input when paused", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.paused,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("chat");

    // Should show paused state indicator
    await expect(
      page.getByText(/Input Required|paused|waiting/i),
    ).toBeVisible();
  });

  test("should allow typing in chat input", async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.single });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("chat");

    const textarea = page.locator("textarea").first();
    await textarea.fill("Test message");

    await expect(textarea).toHaveValue("Test message");
  });

  test("should show response placeholder for paused workflow", async ({
    page,
  }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.paused,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("chat");

    await expect(
      page.getByPlaceholder(/response|continue|message/i),
    ).toBeVisible();
  });
});
