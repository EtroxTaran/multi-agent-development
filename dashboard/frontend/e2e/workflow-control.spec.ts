/**
 * Journey 4: Workflow Control (P1)
 * Tests for starting, pausing, resuming, and resetting workflows
 */

import { test, expect } from "@playwright/test";
import { ProjectDashboardPage } from "./page-objects";
import {
  setupApiMocks,
  overrideApiMock,
  mockProjects,
  mockWorkflowStatus,
} from "./fixtures";

test.describe("Workflow Control", () => {
  test("should show start workflow button for not started projects", async ({
    page,
  }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.notStarted,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await expect(dashboardPage.startWorkflowButton).toBeVisible();
  });

  test("should open start workflow dialog", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.notStarted,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.clickStartWorkflow();

    await expect(
      page.getByRole("heading", { name: "Start Workflow" }),
    ).toBeVisible();
    await expect(page.getByText("Start Phase")).toBeVisible();
    await expect(page.getByText("End Phase")).toBeVisible();
    await expect(page.getByLabel("Skip Validation")).toBeVisible();
    await expect(page.getByLabel("Autonomous")).toBeVisible();
  });

  test("should show pause button for in-progress workflow", async ({
    page,
  }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.inProgress,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await expect(dashboardPage.pauseButton).toBeVisible();
  });

  test("should show resume button for paused workflow", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.paused,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await expect(dashboardPage.resumeButton).toBeVisible();
  });

  test("should show pending interrupt info when paused", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.paused,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await expect(page.getByText("paused")).toBeVisible();
  });

  test("should handle workflow start action", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.notStarted,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Open dialog
    await dashboardPage.clickStartWorkflow();

    // Update status after start
    await overrideApiMock(
      page,
      "/api/projects/test-project/workflow/status",
      mockWorkflowStatus.inProgress,
    );

    // Click start in dialog
    const startButton = page.getByRole("button", {
      name: "Start",
      exact: true,
    });
    await startButton.click();

    // Should update status
    await expect(page.getByText("in_progress")).toBeVisible({ timeout: 5000 });
  });
});
