/**
 * Journey 3: Complete Project Lifecycle (P1)
 * Tests for creating, viewing, and managing projects through their lifecycle
 */

import { test, expect } from "@playwright/test";
import { ProjectsPage, ProjectDashboardPage } from "./page-objects";
import {
  setupApiMocks,
  overrideApiMock,
  mockProjects,
  mockWorkflowStatus,
  mockTasks,
} from "./fixtures";

test.describe("Project Lifecycle", () => {
  test("should create a new project", async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.empty });

    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    // Open new project form
    await projectsPage.clickNewProject();
    await expect(projectsPage.newProjectForm).toBeVisible();

    // Fill project name
    await projectsPage.projectNameInput.fill("my-new-project");

    // Update mock to include new project after creation
    await overrideApiMock(page, "/api/projects", [
      {
        name: "my-new-project",
        path: "/tmp/my-new-project",
        current_phase: 0,
        workflow_status: "not_started",
        has_documents: false,
      },
    ]);

    // Submit
    await projectsPage.createButton.click();

    // Should show the new project
    await expect(page.getByText("my-new-project")).toBeVisible();
  });

  test("should cancel project creation", async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.single });

    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    await projectsPage.clickNewProject();
    await projectsPage.projectNameInput.fill("cancelled-project");
    await projectsPage.cancelNewProject();

    // Form should be hidden
    await expect(projectsPage.newProjectForm).not.toBeVisible();
  });

  test("should display project details on dashboard", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.inProgress,
      tasks: mockTasks.inProgress,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Check project info is displayed
    await expect(dashboardPage.projectTitle).toContainText("test-project");
    await expect(dashboardPage.statusBadge).toBeVisible();

    // Check stats cards are visible
    await expect(dashboardPage.currentPhaseCard).toBeVisible();
    await expect(dashboardPage.taskProgressCard).toBeVisible();
    await expect(dashboardPage.agentsCard).toBeVisible();
    await expect(dashboardPage.commitsCard).toBeVisible();
  });

  test("should show current phase information", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.inProgress,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    const phase = await dashboardPage.getCurrentPhase();
    expect(phase).toContain("2");
  });

  test("should show task progress", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      tasks: mockTasks.inProgress,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    const progress = await dashboardPage.getTaskProgress();
    expect(progress).toContain("1/3");
  });

  test("should display all dashboard tabs", async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.single });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await expect(dashboardPage.graphTab).toBeVisible();
    await expect(dashboardPage.tasksTab).toBeVisible();
    await expect(dashboardPage.agentsTab).toBeVisible();
    await expect(dashboardPage.budgetTab).toBeVisible();
    await expect(dashboardPage.chatTab).toBeVisible();
    await expect(dashboardPage.errorsTab).toBeVisible();
  });

  test("should switch between tabs", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      tasks: mockTasks.inProgress,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Default is graph tab
    await expect(dashboardPage.graphTab).toHaveAttribute(
      "data-state",
      "active",
    );

    // Switch to tasks tab
    await dashboardPage.switchToTab("tasks");
    await expect(dashboardPage.tasksTab).toHaveAttribute(
      "data-state",
      "active",
    );

    // Check task content is visible
    await expect(page.getByText("Pending")).toBeVisible();
  });

  test("should show completed workflow state", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      workflowStatus: mockWorkflowStatus.completed,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await expect(page.getByText("completed")).toBeVisible();
  });
});
