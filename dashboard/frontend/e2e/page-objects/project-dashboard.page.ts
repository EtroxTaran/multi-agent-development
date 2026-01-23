/**
 * Project dashboard page object
 */

import { Page, Locator, expect } from "@playwright/test";
import { BasePage } from "./base.page";

export class ProjectDashboardPage extends BasePage {
  // Header elements
  readonly projectTitle: Locator;
  readonly statusBadge: Locator;
  readonly liveBadge: Locator;
  readonly healthBadge: Locator;

  // Action buttons
  readonly startWorkflowButton: Locator;
  readonly resumeButton: Locator;
  readonly pauseButton: Locator;

  // Stats cards
  readonly currentPhaseCard: Locator;
  readonly taskProgressCard: Locator;
  readonly agentsCard: Locator;
  readonly commitsCard: Locator;

  // Tabs
  readonly tabsList: Locator;
  readonly graphTab: Locator;
  readonly tasksTab: Locator;
  readonly agentsTab: Locator;
  readonly budgetTab: Locator;
  readonly chatTab: Locator;
  readonly errorsTab: Locator;

  // Tab content
  readonly graphContent: Locator;
  readonly tasksContent: Locator;
  readonly agentsContent: Locator;
  readonly budgetContent: Locator;
  readonly chatContent: Locator;
  readonly errorsContent: Locator;

  // Loading and error states
  readonly loadingSpinner: Locator;
  readonly errorMessage: Locator;
  readonly notFoundMessage: Locator;

  constructor(page: Page) {
    super(page);

    // Header
    this.projectTitle = page.locator("h1.text-3xl");
    this.statusBadge = page.locator('h1 + [class*="Badge"]').first();
    this.liveBadge = page.getByText("Live");
    this.healthBadge = page
      .locator('[class*="Badge"][class*="outline"]')
      .last();

    // Action buttons
    this.startWorkflowButton = page.getByRole("button", {
      name: "Start Workflow",
    });
    this.resumeButton = page.getByRole("button", { name: "Resume" });
    this.pauseButton = page.getByRole("button", { name: "Pause" });

    // Stats cards
    this.currentPhaseCard = page
      .locator('[class*="Card"]')
      .filter({ hasText: "Current Phase" });
    this.taskProgressCard = page
      .locator('[class*="Card"]')
      .filter({ hasText: "Task Progress" });
    this.agentsCard = page
      .locator('[class*="Card"]')
      .filter({ hasText: "Agents" });
    this.commitsCard = page
      .locator('[class*="Card"]')
      .filter({ hasText: "Commits" });

    // Tabs
    this.tabsList = page.getByRole("tablist");
    this.graphTab = page.getByRole("tab", { name: "Graph" });
    this.tasksTab = page.getByRole("tab", { name: "Tasks" });
    this.agentsTab = page.getByRole("tab", { name: "Agents" });
    this.budgetTab = page.getByRole("tab", { name: "Budget" });
    this.chatTab = page.getByRole("tab", { name: "Chat" });
    this.errorsTab = page.getByRole("tab", { name: "Errors" });

    // Tab content panels
    this.graphContent = page
      .locator('[role="tabpanel"][data-state="active"]')
      .filter({ has: page.locator(".react-flow") });
    this.tasksContent = page
      .locator('[role="tabpanel"]')
      .filter({ hasText: "Pending" });
    this.agentsContent = page
      .locator('[role="tabpanel"]')
      .filter({ hasText: "claude" });
    this.budgetContent = page
      .locator('[role="tabpanel"]')
      .filter({ hasText: "spent" });
    this.chatContent = page
      .locator('[role="tabpanel"]')
      .filter({ has: page.locator("textarea") });
    this.errorsContent = page
      .locator('[role="tabpanel"]')
      .filter({ hasText: "Error" });

    // Loading and error states
    this.loadingSpinner = page.locator(".animate-spin");
    this.errorMessage = page.locator(".text-destructive");
    this.notFoundMessage = page.getByText("Project not found");
  }

  /**
   * Navigate to project dashboard
   */
  async goto(projectName: string) {
    await this.page.goto(`/project/${projectName}`);
    await this.waitForPageLoad();
  }

  /**
   * Wait for dashboard to load
   */
  async waitForDashboardToLoad() {
    await expect(this.projectTitle).toBeVisible();
    await this.page.waitForLoadState("networkidle");
  }

  /**
   * Get project name from title
   */
  async getProjectName(): Promise<string> {
    return this.projectTitle.textContent() || "";
  }

  /**
   * Get current workflow status
   */
  async getWorkflowStatus(): Promise<string> {
    return this.statusBadge.textContent() || "";
  }

  /**
   * Check if connected to WebSocket
   */
  async isLive(): Promise<boolean> {
    return this.liveBadge.isVisible();
  }

  /**
   * Click start workflow button
   */
  async clickStartWorkflow() {
    await this.startWorkflowButton.click();
  }

  /**
   * Click resume button
   */
  async clickResume() {
    await this.resumeButton.click();
  }

  /**
   * Click pause button
   */
  async clickPause() {
    await this.pauseButton.click();
  }

  /**
   * Switch to a specific tab
   */
  async switchToTab(
    tabName: "graph" | "tasks" | "agents" | "budget" | "chat" | "errors",
  ) {
    const tabMap = {
      graph: this.graphTab,
      tasks: this.tasksTab,
      agents: this.agentsTab,
      budget: this.budgetTab,
      chat: this.chatTab,
      errors: this.errorsTab,
    };
    await tabMap[tabName].click();
  }

  /**
   * Get current phase from stats card
   */
  async getCurrentPhase(): Promise<string> {
    const content = await this.currentPhaseCard
      .locator(".text-2xl")
      .textContent();
    return content || "";
  }

  /**
   * Get task progress from stats card
   */
  async getTaskProgress(): Promise<string> {
    const content = await this.taskProgressCard
      .locator(".text-2xl")
      .textContent();
    return content || "";
  }

  /**
   * Get commit count from stats card
   */
  async getCommitCount(): Promise<string> {
    const content = await this.commitsCard.locator(".text-2xl").textContent();
    return content || "";
  }

  /**
   * Check if agent is available
   */
  async isAgentAvailable(agentName: string): Promise<boolean> {
    const agentBadge = this.agentsCard.locator(
      `[class*="Badge"]:has-text("${agentName}")`,
    );
    const classList = await agentBadge.getAttribute("class");
    return classList?.includes("success") ?? false;
  }
}
