/**
 * Journey 5: WebSocket Real-Time Updates (P1)
 * Tests for real-time updates via WebSocket
 */

import { test, expect } from "@playwright/test";
import { ProjectDashboardPage } from "./page-objects";
import {
  setupApiMocks,
  mockProjects,
  mockWorkflowStatus,
  mockTasks,
} from "./fixtures";

test.describe("WebSocket Updates", () => {
  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.inProgress,
      tasks: mockTasks.inProgress,
    });
  });

  test("should show live indicator when connected", async ({ page }) => {
    // Mock WebSocket connection
    await page.addInitScript(() => {
      // Override WebSocket to simulate connection
      const OriginalWebSocket = window.WebSocket;
      (window as unknown as { WebSocket: typeof WebSocket }).WebSocket =
        class extends OriginalWebSocket {
          constructor(url: string | URL, protocols?: string | string[]) {
            super(url, protocols);
            // Simulate successful connection
            setTimeout(() => {
              this.dispatchEvent(new Event("open"));
            }, 100);
          }
        };
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Wait for connection indicator
    await expect(dashboardPage.liveBadge).toBeVisible({ timeout: 5000 });
  });

  test("should display workflow graph nodes", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Switch to graph tab
    await dashboardPage.switchToTab("graph");

    // Check nodes are visible
    await expect(page.getByText("Planning")).toBeVisible();
    await expect(page.getByText("Implementation")).toBeVisible();
  });

  test("should show phase progress component", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Phase progress should show current phase info
    await expect(page.getByText(/Phase 1|Planning/)).toBeVisible();
    await expect(page.getByText(/Phase 2|Validation/)).toBeVisible();
  });

  test("should update task list when viewing tasks tab", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("tasks");

    // Should show task list with mock data
    await expect(page.getByText("Set up project structure")).toBeVisible();
    await expect(page.getByText("Implement core logic")).toBeVisible();
    await expect(page.getByText("Add documentation")).toBeVisible();
  });

  test("should show agent statuses in agents tab", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("agents");

    // Should show agent information
    await expect(page.getByText("claude")).toBeVisible();
    await expect(page.getByText("cursor")).toBeVisible();
    await expect(page.getByText("gemini")).toBeVisible();
  });
});
