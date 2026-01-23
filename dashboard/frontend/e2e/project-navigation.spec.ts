/**
 * Journey 1: Project List & Navigation (P0)
 * Tests for viewing and navigating between projects
 */

import { test, expect } from "@playwright/test";
import { ProjectsPage, ProjectDashboardPage } from "./page-objects";
import {
  setupApiMocks,
  mockProjects,
  mockWorkflowStatus,
  mockWorkflowHealth,
  mockTasks,
} from "./fixtures";

test.describe("Project Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.multiple,
    });
  });

  test("should display projects list on home page", async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    await expect(projectsPage.heading).toBeVisible();
    await expect(page.getByText("project-alpha")).toBeVisible();
    await expect(page.getByText("project-beta")).toBeVisible();
    await expect(page.getByText("project-gamma")).toBeVisible();
  });

  test("should show project count correctly", async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    const count = await projectsPage.getProjectCount();
    expect(count).toBe(3);
  });

  test("should display project status badges", async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    // Check different status badges
    await expect(page.getByText("in_progress")).toBeVisible();
    await expect(page.getByText("completed")).toBeVisible();
    await expect(page.getByText("not_started")).toBeVisible();
  });

  test("should navigate to project dashboard on click", async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    // Set up dashboard mocks
    await setupApiMocks(page, {
      workflowStatus: mockWorkflowStatus.inProgress,
      workflowHealth: mockWorkflowHealth.healthy,
      tasks: mockTasks.inProgress,
    });

    await projectsPage.openProject("project-alpha");

    const dashboardPage = new ProjectDashboardPage(page);
    await expect(dashboardPage.projectTitle).toContainText("project-alpha");
  });

  test("should handle empty projects list", async ({ page }) => {
    await setupApiMocks(page, { projects: mockProjects.empty });

    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    await expect(projectsPage.emptyState).toBeVisible();
    await expect(page.getByText("Create your first project")).toBeVisible();
  });
});
