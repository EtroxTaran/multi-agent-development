/**
 * Journey 6: Task Management & Kanban (P2)
 * Tests for viewing and managing tasks
 */

import { test, expect } from "@playwright/test";
import { ProjectDashboardPage } from "./page-objects";
import { setupApiMocks, mockProjects, mockTasks } from "./fixtures";

test.describe("Task Management", () => {
  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      tasks: mockTasks.inProgress,
    });
  });

  test("should display task board with columns", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("tasks");

    // Should show status columns
    await expect(page.getByText("Pending").first()).toBeVisible();
    await expect(page.getByText("In Progress").first()).toBeVisible();
    await expect(page.getByText("Completed").first()).toBeVisible();
  });

  test("should show task cards with details", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("tasks");

    // Check task titles are visible
    await expect(page.getByText("Set up project structure")).toBeVisible();
    await expect(page.getByText("Implement core logic")).toBeVisible();
    await expect(page.getByText("Add documentation")).toBeVisible();
  });

  test("should show task counts in header stats", async ({ page }) => {
    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    // Task progress should show completed/total
    const progress = await dashboardPage.getTaskProgress();
    expect(progress).toBe("1/3");
  });

  test("should show task with failure state", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      tasks: mockTasks.withFailure,
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    await dashboardPage.switchToTab("tasks");

    // Should show failed task
    await expect(page.getByText("failed")).toBeVisible();
  });

  test("should show empty state when no tasks", async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
      tasks: {
        tasks: [],
        total: 0,
        completed: 0,
        in_progress: 0,
        pending: 0,
        failed: 0,
      },
    });

    const dashboardPage = new ProjectDashboardPage(page);
    await dashboardPage.goto("test-project");

    const progress = await dashboardPage.getTaskProgress();
    expect(progress).toBe("0/0");
  });
});
