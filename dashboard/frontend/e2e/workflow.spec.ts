/**
 * Workflow visualization tests (migrated to use page objects)
 */

import { test, expect } from "@playwright/test";
import { ProjectDashboardPage } from "./page-objects";
import {
  setupApiMocks,
  overrideApiMock,
  mockProjects,
  mockWorkflowStatus,
} from "./fixtures";

test.describe("Workflow Visualization", () => {
  const projectName = "test-project";

  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.notStarted,
    });
  });

  test("should display workflow graph tab", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto(projectName);

    // Check tabs are visible
    await expect(dashboardPage.graphTab).toBeVisible();
    await expect(dashboardPage.tasksTab).toBeVisible();
    await expect(dashboardPage.chatTab).toBeVisible();

    // Click Graph tab
    await dashboardPage.switchToTab("graph");

    // Check graph nodes are visible
    await expect(page.getByText("Planning")).toBeVisible();
    await expect(page.getByText("Implementation")).toBeVisible();
  });

  test("should open start workflow dialog", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto(projectName);

    // Click Start Workflow button
    await dashboardPage.clickStartWorkflow();

    // Check dialog content
    await expect(
      page.getByRole("heading", { name: "Start Workflow" }),
    ).toBeVisible();
    await expect(page.getByText("Start Phase")).toBeVisible();
    await expect(page.getByText("End Phase")).toBeVisible();
    await expect(page.getByLabel("Skip Validation")).toBeVisible();
    await expect(page.getByLabel("Autonomous")).toBeVisible();
  });

  test("should display HITL chat state", async ({ page }) => {
    // Override status to be paused
    await overrideApiMock(
      page,
      `/api/projects/${projectName}/workflow/status`,
      mockWorkflowStatus.paused,
    );

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto(projectName);

    // Click Chat tab
    await dashboardPage.switchToTab("chat");

    // Check for paused indicator
    await expect(
      page.getByText(/Input Required|paused|waiting/i),
    ).toBeVisible();
  });
});
