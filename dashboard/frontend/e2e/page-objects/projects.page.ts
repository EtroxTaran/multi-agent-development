/**
 * Projects list page object
 */

import { Page, Locator, expect } from "@playwright/test";
import { BasePage } from "./base.page";

export class ProjectsPage extends BasePage {
  // Locators
  readonly heading: Locator;
  readonly newProjectButton: Locator;
  readonly refreshButton: Locator;
  readonly projectCards: Locator;
  readonly loadingSpinner: Locator;
  readonly emptyState: Locator;
  readonly errorMessage: Locator;
  readonly retryButton: Locator;

  // New project form
  readonly newProjectForm: Locator;
  readonly projectNameInput: Locator;
  readonly createButton: Locator;
  readonly cancelButton: Locator;
  readonly createError: Locator;

  constructor(page: Page) {
    super(page);

    this.heading = page.getByRole("heading", { name: "Projects" });
    this.newProjectButton = page.getByRole("button", { name: "New Project" });
    this.refreshButton = page.getByRole("button", { name: "Refresh" });
    this.projectCards = page.locator('[class*="grid"] a[href^="/project/"]');
    this.loadingSpinner = page.locator(".animate-spin");
    this.emptyState = page.getByText("No projects yet");
    this.errorMessage = page.locator(".text-destructive");
    this.retryButton = page.getByRole("button", { name: "Retry" });

    // New project form
    this.newProjectForm = page
      .locator('[class*="Card"]')
      .filter({ hasText: "Create New Project" });
    this.projectNameInput = page.getByPlaceholder("Project name");
    this.createButton = page.getByRole("button", {
      name: "Create",
      exact: true,
    });
    this.cancelButton = page.getByRole("button", { name: "Cancel" });
    this.createError = page
      .locator(".text-destructive")
      .filter({ hasText: "Failed" });
  }

  /**
   * Navigate to projects page
   */
  async goto() {
    await this.page.goto("/");
    await this.waitForPageLoad();
  }

  /**
   * Wait for projects list to load
   */
  async waitForProjectsToLoad() {
    await expect(this.heading).toBeVisible();
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Click new project button
   */
  async clickNewProject() {
    await this.newProjectButton.click();
    await expect(this.newProjectForm).toBeVisible();
  }

  /**
   * Create a new project
   */
  async createProject(name: string) {
    await this.clickNewProject();
    await this.projectNameInput.fill(name);
    await this.createButton.click();
  }

  /**
   * Get project card by name
   */
  getProjectCard(name: string): Locator {
    return this.page.locator(`a[href="/project/${name}"]`);
  }

  /**
   * Click on a project to navigate to its dashboard
   */
  async openProject(name: string) {
    await this.getProjectCard(name).click();
  }

  /**
   * Get project count
   */
  async getProjectCount(): Promise<number> {
    return this.projectCards.count();
  }

  /**
   * Check if project exists in list
   */
  async projectExists(name: string): Promise<boolean> {
    const card = this.getProjectCard(name);
    return card.isVisible();
  }

  /**
   * Refresh project list
   */
  async refresh() {
    await this.refreshButton.click();
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Cancel new project form
   */
  async cancelNewProject() {
    await this.cancelButton.click();
    await expect(this.newProjectForm).not.toBeVisible();
  }

  /**
   * Get project status badge
   */
  getProjectStatus(name: string): Locator {
    return this.getProjectCard(name).locator('[class*="Badge"]').first();
  }
}
