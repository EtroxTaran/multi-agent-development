/**
 * Mock data for E2E tests
 */

export const mockProjects = {
  empty: [],

  single: [
    {
      name: "test-project",
      path: "/tmp/test-project",
      created_at: new Date().toISOString(),
      current_phase: 0,
      has_documents: false,
      has_product_spec: false,
      has_claude_md: false,
      has_gemini_md: false,
      has_cursor_rules: false,
      workflow_status: "not_started",
    },
  ],

  multiple: [
    {
      name: "project-alpha",
      path: "/tmp/project-alpha",
      created_at: new Date(Date.now() - 86400000).toISOString(),
      current_phase: 3,
      has_documents: true,
      has_product_spec: true,
      has_claude_md: true,
      has_gemini_md: true,
      has_cursor_rules: true,
      workflow_status: "in_progress",
    },
    {
      name: "project-beta",
      path: "/tmp/project-beta",
      created_at: new Date(Date.now() - 172800000).toISOString(),
      current_phase: 5,
      has_documents: true,
      has_product_spec: true,
      has_claude_md: true,
      has_gemini_md: false,
      has_cursor_rules: false,
      workflow_status: "completed",
    },
    {
      name: "project-gamma",
      path: "/tmp/project-gamma",
      created_at: new Date().toISOString(),
      current_phase: 0,
      has_documents: false,
      has_product_spec: false,
      has_claude_md: false,
      has_gemini_md: false,
      has_cursor_rules: false,
      workflow_status: "not_started",
    },
  ],
};

export const mockWorkflowStatus = {
  notStarted: {
    mode: "langgraph",
    status: "not_started",
    project: "test-project",
    current_phase: 0,
    phase_status: {},
    pending_interrupt: null,
  },

  inProgress: {
    mode: "langgraph",
    status: "in_progress",
    project: "test-project",
    current_phase: 2,
    phase_status: {
      "1": "completed",
      "2": "in_progress",
    },
    pending_interrupt: null,
  },

  paused: {
    mode: "langgraph",
    status: "paused",
    project: "test-project",
    current_phase: 3,
    phase_status: {
      "1": "completed",
      "2": "completed",
      "3": "paused",
    },
    pending_interrupt: {
      type: "approval_gate",
      message: "Waiting for approval",
      paused_at: ["approval_gate"],
    },
  },

  completed: {
    mode: "langgraph",
    status: "completed",
    project: "test-project",
    current_phase: 5,
    phase_status: {
      "1": "completed",
      "2": "completed",
      "3": "completed",
      "4": "completed",
      "5": "completed",
    },
    pending_interrupt: null,
  },

  failed: {
    mode: "langgraph",
    status: "failed",
    project: "test-project",
    current_phase: 3,
    phase_status: {
      "1": "completed",
      "2": "completed",
      "3": "failed",
    },
    pending_interrupt: null,
    message: "Implementation failed: tests not passing",
  },
};

export const mockWorkflowHealth = {
  healthy: {
    status: "healthy",
    project: "test-project",
    current_phase: 2,
    phase_status: "in_progress",
    iteration_count: 3,
    last_updated: new Date().toISOString(),
    agents: { claude: true, cursor: true, gemini: true },
    langgraph_enabled: true,
    has_context: true,
    total_commits: 5,
  },

  degraded: {
    status: "degraded",
    project: "test-project",
    current_phase: 2,
    agents: { claude: true, cursor: false, gemini: true },
    langgraph_enabled: true,
    has_context: true,
    total_commits: 3,
  },

  unhealthy: {
    status: "unhealthy",
    project: "test-project",
    agents: { claude: false, cursor: false, gemini: false },
    langgraph_enabled: false,
    has_context: false,
    total_commits: 0,
  },
};

export const mockTasks = {
  empty: {
    tasks: [],
    total: 0,
    completed: 0,
    in_progress: 0,
    pending: 0,
    failed: 0,
  },

  inProgress: {
    tasks: [
      {
        id: "T1",
        title: "Set up project structure",
        description: "Initialize the basic project structure",
        status: "completed",
        priority: 1,
        dependencies: [],
        files_to_create: ["src/index.ts"],
        files_to_modify: [],
        acceptance_criteria: ["Project compiles"],
        complexity_score: 2.0,
        created_at: new Date(Date.now() - 3600000).toISOString(),
        completed_at: new Date(Date.now() - 1800000).toISOString(),
      },
      {
        id: "T2",
        title: "Implement core logic",
        description: "Implement the main business logic",
        status: "in_progress",
        priority: 2,
        dependencies: ["T1"],
        files_to_create: ["src/core.ts"],
        files_to_modify: ["src/index.ts"],
        acceptance_criteria: ["Tests pass", "No lint errors"],
        complexity_score: 4.5,
        created_at: new Date(Date.now() - 1800000).toISOString(),
        started_at: new Date(Date.now() - 900000).toISOString(),
      },
      {
        id: "T3",
        title: "Add documentation",
        description: "Write API documentation",
        status: "pending",
        priority: 3,
        dependencies: ["T2"],
        files_to_create: ["docs/API.md"],
        files_to_modify: [],
        acceptance_criteria: ["All public APIs documented"],
        complexity_score: 2.0,
        created_at: new Date(Date.now() - 1800000).toISOString(),
      },
    ],
    total: 3,
    completed: 1,
    in_progress: 1,
    pending: 1,
    failed: 0,
  },

  withFailure: {
    tasks: [
      {
        id: "T1",
        title: "Setup database",
        status: "completed",
        priority: 1,
      },
      {
        id: "T2",
        title: "Implement API",
        status: "failed",
        priority: 2,
        error: "Tests failed: 3 assertions failed",
      },
      {
        id: "T3",
        title: "Add frontend",
        status: "blocked",
        priority: 3,
        dependencies: ["T2"],
      },
    ],
    total: 3,
    completed: 1,
    in_progress: 0,
    pending: 0,
    failed: 1,
  },
};

export const mockBudget = {
  normal: {
    total_spent_usd: 1.25,
    project_budget_usd: 10.0,
    project_remaining_usd: 8.75,
    project_used_percent: 12.5,
    task_count: 3,
    record_count: 15,
    task_spent: { T1: 0.75, T2: 0.5 },
    updated_at: new Date().toISOString(),
    enabled: true,
  },

  nearLimit: {
    total_spent_usd: 9.5,
    project_budget_usd: 10.0,
    project_remaining_usd: 0.5,
    project_used_percent: 95.0,
    task_count: 5,
    record_count: 50,
    task_spent: { T1: 2.0, T2: 3.0, T3: 2.5, T4: 1.5, T5: 0.5 },
    updated_at: new Date().toISOString(),
    enabled: true,
  },

  disabled: {
    total_spent_usd: 0,
    project_budget_usd: null,
    project_remaining_usd: null,
    project_used_percent: null,
    task_count: 0,
    record_count: 0,
    task_spent: {},
    updated_at: null,
    enabled: false,
  },
};

export const mockAgents = [
  {
    agent: "claude",
    available: true,
    last_invocation: new Date(Date.now() - 60000).toISOString(),
    total_invocations: 25,
    success_rate: 0.92,
    avg_duration_seconds: 45.5,
    total_cost_usd: 1.25,
  },
  {
    agent: "cursor",
    available: true,
    last_invocation: new Date(Date.now() - 120000).toISOString(),
    total_invocations: 15,
    success_rate: 0.87,
    avg_duration_seconds: 30.2,
    total_cost_usd: 0.0,
  },
  {
    agent: "gemini",
    available: true,
    last_invocation: new Date(Date.now() - 180000).toISOString(),
    total_invocations: 10,
    success_rate: 0.9,
    avg_duration_seconds: 25.8,
    total_cost_usd: 0.35,
  },
];

export const mockWorkflowGraph = {
  nodes: [
    { id: "planning", data: { label: "Planning" } },
    { id: "cursor_validate", data: { label: "Cursor Validation" } },
    { id: "gemini_validate", data: { label: "Gemini Validation" } },
    { id: "implementation", data: { label: "Implementation" } },
    { id: "cursor_review", data: { label: "Cursor Review" } },
    { id: "gemini_review", data: { label: "Gemini Review" } },
    { id: "completion", data: { label: "Completion" } },
  ],
  edges: [
    { source: "planning", target: "cursor_validate" },
    { source: "planning", target: "gemini_validate" },
    { source: "cursor_validate", target: "implementation" },
    { source: "gemini_validate", target: "implementation" },
    { source: "implementation", target: "cursor_review" },
    { source: "implementation", target: "gemini_review" },
    { source: "cursor_review", target: "completion" },
    { source: "gemini_review", target: "completion" },
  ],
};

export const mockProject = {
  name: "test-project",
  path: "/tmp/test-project",
  config: {},
  state: { current_phase: 1 },
  files: {
    "Docs/PRODUCT.md": true,
    "CLAUDE.md": true,
    "GEMINI.md": false,
  },
  phases: {},
};
