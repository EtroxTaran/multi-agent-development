/**
 * Journey 8: Agent Performance Monitoring (P2)
 * Tests for viewing agent status and performance
 */

import { test, expect } from "@playwright/test";
import { ProjectDashboardPage } from "./page-objects";
import {
  setupApiMocks,
  mockProjects,
  mockAgents,
  mockWorkflowHealth,
} from "./fixtures";

test.describe("Agent Monitoring", () => {
  test("should display agent status in header", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowHealth: mockWorkflowHealth.healthy,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Should show agent badges in stats card
    await expect(dashboardPage.agentsCard).toBeVisible();
    await expect(page.getByText("claude")).toBeVisible();
    await expect(page.getByText("cursor")).toBeVisible();
    await expect(page.getByText("gemini")).toBeVisible();
  });

  test("should display detailed agent info in agents tab", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      agents: mockAgents,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("agents");

    // Should show agent details
    await expect(page.getByText("claude")).toBeVisible();
    await expect(page.getByText(/invocation|total/i)).toBeVisible();
  });

  test("should show unavailable agent state", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowHealth: mockWorkflowHealth.degraded,
      agents: [
        {
          agent: "claude",
          available: true,
          total_invocations: 10,
          success_rate: 0.9,
        },
        {
          agent: "cursor",
          available: false,
          total_invocations: 5,
          success_rate: 0.0,
        },
        {
          agent: "gemini",
          available: true,
          total_invocations: 8,
          success_rate: 0.85,
        },
      ],
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Should show degraded status
    await expect(page.getByText("degraded")).toBeVisible();
  });

  test("should show health status badge", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowHealth: mockWorkflowHealth.healthy,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await expect(page.getByText("healthy")).toBeVisible();
  });
});
