/**
 * Journey 2: Error Handling & Resilience (P0)
 * Tests for error states and recovery
 */

import { test, expect } from "@playwright/test";
import { ProjectsPage, ProjectDashboardPage } from "./page-objects";
import {
  setupApiMocks,
  failApiMock,
  timeoutApiMock,
  mockProjects,
  mockWorkflowStatus,
} from "./fixtures";

test.describe("Error Handling", () => {
  test("should show error message when projects API fails", async ({
    page,
  }) => {
    await failApiMock(page, "/api/projects", 500, "Server error");

    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    await expect(projectsPage.errorMessage).toBeVisible();
    await expect(projectsPage.retryButton).toBeVisible();
  });

  test("should retry loading projects on click", async ({ page }) => {
    // First request fails
    let requestCount = 0;
    await page.route("/api/projects", async (route) => {
      requestCount++;
      if (requestCount === 1) {
        await route.fulfill({ status: 500, json: { error: "Server error" } });
      } else {
        await route.fulfill({ json: mockProjects.single });
      }
    });

    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    // Should show error initially
    await expect(projectsPage.errorMessage).toBeVisible();

    // Click retry
    await projectsPage.retryButton.click();

    // Should show project list after retry
    await expect(page.getByText("test-project")).toBeVisible();
  });

  test("should show project not found on dashboard", async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.single });
    await failApiMock(
      page,
      "/api/projects/nonexistent",
      404,
      "Project not found",
    );

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("nonexistent");

    await expect(dashboardPage.errorMessage).toBeVisible();
  });

  test("should handle workflow status API failure gracefully", async ({
    page,
  }) => {
    await setupApiMocks(page, { projects: mockProjects.single });
    await failApiMock(
      page,
      "/api/projects/*/workflow/status",
      500,
      "Workflow error",
    );

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Dashboard should still load, but may show error state
    await expect(dashboardPage.projectTitle).toBeVisible();
  });

  test("should show degraded state when agent unavailable", async ({
    page,
  }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowHealth: {
        status: "degraded",
        project: "test-project",
        current_phase: 2,
        agents: { claude: true, cursor: false, gemini: true },
        langgraph_enabled: true,
        has_context: true,
        total_commits: 3,
      },
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await expect(page.getByText("degraded")).toBeVisible();
  });

  test("should handle project creation failure", async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.single });
    await failApiMock(
      page,
      "/api/projects/*/init",
      400,
      "Project already exists",
    );

    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    await projectsPage.createProject("existing-project");

    // Should show error message
    await expect(page.getByText(/Failed|exists/i)).toBeVisible();
  });

  test("should handle workflow start failure", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.notStarted,
    });

    // Mock start failure
    await failApiMock(
      page,
      "/api/projects/*/start",
      400,
      "Prerequisites not met: No documentation found",
    );

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Click start
    await dashboardPage.clickStartWorkflow();

    // Check that we are in the dialog
    await expect(page.getByRole("dialog")).toBeVisible();

    // Click confirm start
    await page.getByRole("button", { name: "Start" }).click();

    // Should show error message in the dialog
    await expect(page.getByText(/Prerequisites not met/i)).toBeVisible();
  });
});
