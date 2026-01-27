/**
 * MSW handlers for API mocking
 */

import { http, HttpResponse } from "msw";
import type {
  ProjectSummary,
  ProjectStatus,
  WorkflowStatusResponse,
  WorkflowHealthResponse,
  TaskListResponse,
  TaskInfo,
  AgentStatusResponse,
  BudgetStatus,
} from "@/types";

// Mock data
export const mockProjects: ProjectSummary[] = [
  {
    name: "test-project",
    path: "/projects/test-project",
    workflow_status: "not_started",
    current_phase: 0,
    has_documents: true,
    has_product_spec: true,
    has_claude_md: true,
    has_gemini_md: false,
    has_cursor_rules: false,
  },
  {
    name: "active-project",
    path: "/projects/active-project",
    workflow_status: "in_progress",
    current_phase: 2,
    has_documents: true,
    has_product_spec: true,
    has_claude_md: true,
    has_gemini_md: true,
    has_cursor_rules: true,
  },
];

export const mockWorkflowStatus: WorkflowStatusResponse = {
  status: "not_started",
  mode: "langgraph",
  current_phase: 1,
  phase_status: {
    phase_1: "completed",
    phase_2: "in_progress",
    phase_3: "pending",
    phase_4: "pending",
    phase_5: "pending",
  },
};

export const mockWorkflowHealth: WorkflowHealthResponse = {
  status: "healthy",
  project: "test-project",
  current_phase: 1,
  phase_status: "in_progress",
  iteration_count: 3,
  last_updated: new Date().toISOString(),
  agents: {
    claude: true,
    cursor: true,
    gemini: false,
  },
  langgraph_enabled: true,
  has_context: true,
  total_commits: 5,
};

export const mockTasks: TaskInfo[] = [
  {
    id: "task-1",
    title: "Implement feature A",
    description: "Implement the first feature",
    status: "completed",
    complexity_score: 2.5,
    priority: 1,
    files_to_create: ["src/featureA.ts"],
    files_to_modify: [],
    acceptance_criteria: ["Tests pass", "Code reviewed"],
    dependencies: [],
  },
  {
    id: "task-2",
    title: "Implement feature B",
    description: "Implement the second feature",
    status: "in_progress",
    complexity_score: 5.5,
    priority: 2,
    files_to_create: [],
    files_to_modify: ["src/index.ts"],
    acceptance_criteria: ["Tests pass"],
    dependencies: ["task-1"],
  },
];

export const mockAgentStatus: AgentStatusResponse = {
  agents: [
    {
      agent: "claude",
      available: true,
      last_invocation: new Date().toISOString(),
      total_invocations: 10,
      success_rate: 0.9,
      avg_duration_seconds: 45.2,
      total_cost_usd: 1.5,
    },
    {
      agent: "cursor",
      available: true,
      last_invocation: new Date().toISOString(),
      total_invocations: 8,
      success_rate: 0.85,
      avg_duration_seconds: 30.1,
      total_cost_usd: 0.8,
    },
    {
      agent: "gemini",
      available: false,
      total_invocations: 2,
      success_rate: 0.5,
      avg_duration_seconds: 60.0,
      total_cost_usd: 0.3,
    },
  ],
};

export const mockBudgetStatus: BudgetStatus = {
  total_spent_usd: 2.5,
  project_budget_usd: 10.0,
  project_remaining_usd: 7.5,
  project_used_percent: 25.0,
  task_count: 2,
  record_count: 10,
  task_spent: {
    "task-1": 1.5,
    "task-2": 1.0,
  },
  updated_at: new Date().toISOString(),
  enabled: true,
};

// Handlers
export const handlers = [
  // Projects
  http.get("/api/projects", () => {
    return HttpResponse.json(mockProjects);
  }),

  http.get("/api/projects/:name", ({ params }) => {
    const project = mockProjects.find((p) => p.name === params.name);
    if (!project) {
      return HttpResponse.json({ error: "Project not found" }, { status: 404 });
    }
    return HttpResponse.json({
      name: project.name,
      path: project.path,
      files: {
        "CLAUDE.md": project.has_claude_md,
        "GEMINI.md": project.has_gemini_md,
        "Docs/PRODUCT.md": project.has_product_spec,
      },
      phases: {
        phase_1: { exists: true, has_output: true },
        phase_2: { exists: true, has_output: false },
      },
    } as ProjectStatus);
  }),

  http.post("/api/projects/:name/init", ({ params }) => {
    return HttpResponse.json({
      success: true,
      project_dir: `/projects/${params.name}`,
    });
  }),

  http.delete("/api/projects/:name", () => {
    return HttpResponse.json({ message: "Project deleted" });
  }),

  // Workflow
  http.get("/api/projects/:name/status", () => {
    return HttpResponse.json(mockWorkflowStatus);
  }),

  http.get("/api/projects/:name/health", () => {
    return HttpResponse.json(mockWorkflowHealth);
  }),

  http.post("/api/projects/:name/start", () => {
    return HttpResponse.json({
      success: true,
      mode: "langgraph",
      message: "Workflow started",
    });
  }),

  http.post("/api/projects/:name/resume", () => {
    return HttpResponse.json({
      success: true,
      mode: "langgraph",
      message: "Workflow resumed",
    });
  }),

  http.post("/api/projects/:name/pause", () => {
    return HttpResponse.json({ message: "Workflow paused" });
  }),

  http.post("/api/projects/:name/rollback/:phase", ({ params }) => {
    return HttpResponse.json({
      success: true,
      rolled_back_to: `phase_${params.phase}`,
      current_phase: Number(params.phase),
    });
  }),

  http.post("/api/projects/:name/reset", () => {
    return HttpResponse.json({ message: "Workflow reset" });
  }),

  // Tasks
  http.get("/api/projects/:name/tasks", () => {
    return HttpResponse.json({
      tasks: mockTasks,
      total: mockTasks.length,
      completed: mockTasks.filter((t) => t.status === "completed").length,
      in_progress: mockTasks.filter((t) => t.status === "in_progress").length,
      pending: mockTasks.filter((t) => t.status === "pending").length,
    } as TaskListResponse);
  }),

  http.get("/api/projects/:name/tasks/:taskId", ({ params }) => {
    const task = mockTasks.find((t) => t.id === params.taskId);
    if (!task) {
      return HttpResponse.json({ error: "Task not found" }, { status: 404 });
    }
    return HttpResponse.json(task);
  }),

  http.get("/api/projects/:name/tasks/:taskId/history", () => {
    return HttpResponse.json({
      entries: [],
      total: 0,
    });
  }),

  // Agents
  http.get("/api/projects/:name/agents", () => {
    return HttpResponse.json(mockAgentStatus);
  }),

  http.get("/api/projects/:name/audit", () => {
    return HttpResponse.json({ entries: [], total: 0 });
  }),

  http.get("/api/projects/:name/audit/statistics", () => {
    return HttpResponse.json({
      total_invocations: 10,
      successful: 8,
      failed: 2,
      total_cost_usd: 1.5,
      by_agent: {
        claude: { invocations: 6, cost_usd: 1.0 },
        cursor: { invocations: 4, cost_usd: 0.5 },
      },
    });
  }),

  http.get("/api/projects/:name/sessions", () => {
    return HttpResponse.json({ sessions: [] });
  }),

  // Budget
  http.get("/api/projects/:name/budget", () => {
    return HttpResponse.json(mockBudgetStatus);
  }),

  http.get("/api/projects/:name/budget/report", () => {
    return HttpResponse.json({
      report: {
        total_spent_usd: 2.5,
        by_task: {
          "task-1": 1.5,
          "task-2": 1.0,
        },
        by_agent: {
          claude: 2.0,
          cursor: 0.5,
        },
      },
    });
  }),

  // Chat
  http.post("/api/chat", () => {
    return HttpResponse.json({ message: "Response", streaming: false });
  }),

  http.post("/api/chat/command", () => {
    return HttpResponse.json({ success: true, output: "Command executed" });
  }),

  http.get("/api/projects/:name/feedback/:phase", () => {
    return HttpResponse.json({ feedback: "All good" });
  }),

  http.post("/api/projects/:name/escalation/respond", () => {
    return HttpResponse.json({
      message: "Response recorded",
      question_id: "q1",
    });
  }),
];
