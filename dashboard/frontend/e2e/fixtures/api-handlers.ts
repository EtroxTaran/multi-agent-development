/**
 * API mock handlers for E2E tests
 */

import { Page, Route } from "@playwright/test";
import {
  mockProjects,
  mockWorkflowStatus,
  mockWorkflowHealth,
  mockTasks,
  mockBudget,
  mockAgents,
  mockWorkflowGraph,
  mockProject,
} from "./mock-data";

export type MockConfig = {
  projects?:
    | typeof mockProjects.single
    | typeof mockProjects.multiple
    | typeof mockProjects.empty;
  workflowStatus?: (typeof mockWorkflowStatus)[keyof typeof mockWorkflowStatus];
  workflowHealth?: (typeof mockWorkflowHealth)[keyof typeof mockWorkflowHealth];
  tasks?: (typeof mockTasks)[keyof typeof mockTasks];
  budget?: (typeof mockBudget)[keyof typeof mockBudget];
  agents?: typeof mockAgents;
  graph?: typeof mockWorkflowGraph;
  project?: typeof mockProject;
};

/**
 * Set up all API mocks with default values
 */
export async function setupApiMocks(page: Page, config: MockConfig = {}) {
  const {
    projects = mockProjects.single,
    workflowStatus = mockWorkflowStatus.notStarted,
    workflowHealth = mockWorkflowHealth.healthy,
    tasks = mockTasks.empty,
    budget = mockBudget.normal,
    agents = mockAgents,
    graph = mockWorkflowGraph,
    project = mockProject,
  } = config;

  // Projects list
  await page.route("/api/projects", async (route) => {
    await route.fulfill({ json: projects });
  });

  // Project details
  await page.route("/api/projects/*", async (route) => {
    const url = route.request().url();

    // Skip if this is a more specific route
    if (
      url.includes("/workflow") ||
      url.includes("/tasks") ||
      url.includes("/budget") ||
      url.includes("/agents") ||
      url.includes("/audit") ||
      url.includes("/init")
    ) {
      return route.continue();
    }

    await route.fulfill({ json: project });
  });

  // Workflow status
  await page.route("/api/projects/*/workflow/status", async (route) => {
    await route.fulfill({ json: workflowStatus });
  });

  // Workflow health
  await page.route("/api/projects/*/workflow/health", async (route) => {
    await route.fulfill({ json: workflowHealth });
  });

  // Workflow graph
  await page.route("/api/projects/*/workflow/graph", async (route) => {
    await route.fulfill({ json: graph });
  });

  // Tasks
  await page.route("/api/projects/*/tasks", async (route) => {
    await route.fulfill({ json: tasks });
  });

  // Budget
  await page.route("/api/projects/*/budget", async (route) => {
    await route.fulfill({ json: budget });
  });

  // Budget report
  await page.route("/api/projects/*/budget/report", async (route) => {
    await route.fulfill({
      json: {
        status: budget,
        task_spending: Object.entries(budget.task_spent || {}).map(
          ([task_id, spent_usd]) => ({
            task_id,
            spent_usd,
            budget_usd: 2.0,
          }),
        ),
      },
    });
  });

  // Agents
  await page.route("/api/projects/*/agents", async (route) => {
    await route.fulfill({ json: agents });
  });

  // Audit
  await page.route("/api/projects/*/audit", async (route) => {
    await route.fulfill({
      json: {
        entries: [],
        total: 0,
      },
    });
  });

  // Audit statistics
  await page.route("/api/projects/*/audit/statistics", async (route) => {
    await route.fulfill({
      json: {
        total: 50,
        success_count: 45,
        failed_count: 3,
        timeout_count: 2,
        success_rate: 0.9,
        total_cost_usd: 2.5,
        total_duration_seconds: 3600,
        avg_duration_seconds: 72,
        by_agent: { claude: 25, cursor: 15, gemini: 10 },
        by_status: { success: 45, failed: 3, timeout: 2 },
      },
    });
  });

  // Project init
  await page.route("/api/projects/*/init", async (route) => {
    await route.fulfill({
      json: {
        success: true,
        project_dir: "/tmp/new-project",
        message: "Project initialized",
      },
    });
  });

  // Workflow start
  await page.route("/api/projects/*/workflow/start", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        json: {
          success: true,
          mode: "langgraph",
          message: "Workflow started",
        },
      });
    }
  });

  // Workflow resume
  await page.route("/api/projects/*/workflow/resume", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        json: {
          success: true,
          mode: "langgraph",
          message: "Workflow resumed",
        },
      });
    }
  });

  // Workflow reset
  await page.route("/api/projects/*/workflow/reset", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        json: {
          message: "Workflow reset",
        },
      });
    }
  });

  // Workflow rollback
  await page.route("/api/projects/*/workflow/rollback/*", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        json: {
          success: true,
          rolled_back_to: "checkpoint_phase_2",
          current_phase: 2,
          message: "Rolled back successfully",
        },
      });
    }
  });

  // Chat
  await page.route("/api/chat", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        json: {
          message: "This is a mock response from Claude.",
          streaming: false,
        },
      });
    }
  });

  // Chat command
  await page.route("/api/chat/command", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        json: {
          success: true,
          output: "Command executed successfully",
        },
      });
    }
  });
}

/**
 * Override a specific API endpoint
 */
export async function overrideApiMock(
  page: Page,
  pattern: string,
  response: unknown,
  method?: string,
) {
  await page.route(pattern, async (route) => {
    if (!method || route.request().method() === method) {
      await route.fulfill({ json: response });
    } else {
      await route.continue();
    }
  });
}

/**
 * Make an API endpoint fail
 */
export async function failApiMock(
  page: Page,
  pattern: string,
  status: number = 500,
  message: string = "Internal Server Error",
) {
  await page.route(pattern, async (route) => {
    await route.fulfill({
      status,
      json: { error: message, detail: message },
    });
  });
}

/**
 * Make an API endpoint timeout
 */
export async function timeoutApiMock(
  page: Page,
  pattern: string,
  delayMs: number = 30000,
) {
  await page.route(pattern, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.abort("timedout");
  });
}
