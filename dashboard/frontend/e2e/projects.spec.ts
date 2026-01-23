/**
 * Projects page tests (migrated to use page objects)
 */

import { test, expect } from "@playwright/test";
import { ProjectsPage } from "./page-objects";
import { setupApiMocks, overrideApiMock, mockProjects } from "./fixtures";

test.describe("Projects Page", () => {
  test.beforeEach(async ({ page }) => {
    await setupApiMocks(page, {
      projects: mockProjects.single,
    });
  });

  test("should display projects list", async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    await expect(projectsPage.heading).toBeVisible();
    await expect(page.getByText("test-project")).toBeVisible();
  });

  test("should allow creating a new project", async ({ page }) => {
    const projectsPage = new ProjectsPage(page);
    await projectsPage.goto();

    await projectsPage.clickNewProject();
    await expect(page.getByText("Create New Project")).toBeVisible();

    await projectsPage.projectNameInput.fill("new-project");

    // Mock updated projects list after creation
    await overrideApiMock(page, "/api/projects", [
      ...mockProjects.single,
      {
        name: "new-project",
        path: "/tmp/new-project",
        current_phase: 0,
        workflow_status: "not_started",
      },
    ]);

    await projectsPage.createButton.click();

    // Wait for list to update
    await page.waitForTimeout(500);
  });
});
