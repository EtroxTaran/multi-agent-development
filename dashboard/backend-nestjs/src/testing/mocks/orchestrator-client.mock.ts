import { OrchestratorClientService } from "../../orchestrator-client/orchestrator-client.service";

/**
 * Mock factory for OrchestratorClientService
 * Use this in test modules to provide controlled responses
 */
export const createMockOrchestratorClient =
  (): jest.Mocked<OrchestratorClientService> =>
    ({
      // Health
      checkHealth: jest.fn().mockResolvedValue(true),
      onModuleInit: jest.fn().mockResolvedValue(undefined),

      // Projects
      listProjects: jest.fn().mockResolvedValue([]),
      getProject: jest.fn().mockResolvedValue({}),
      initProject: jest.fn().mockResolvedValue({ success: true }),
      deleteProject: jest
        .fn()
        .mockResolvedValue({ message: "Project deleted" }),

      // Workflow
      getWorkflowStatus: jest.fn().mockResolvedValue({
        mode: "langgraph",
        status: "not_started",
        phaseStatus: {},
      }),
      getWorkflowHealth: jest.fn().mockResolvedValue({
        status: "healthy",
        agents: { claude: true, cursor: true, gemini: true },
      }),
      getWorkflowGraph: jest.fn().mockResolvedValue({ nodes: [], edges: [] }),
      startWorkflow: jest
        .fn()
        .mockResolvedValue({ success: true, mode: "langgraph" }),
      resumeWorkflow: jest.fn().mockResolvedValue({ success: true }),
      rollbackWorkflow: jest.fn().mockResolvedValue({ success: true }),
      resetWorkflow: jest.fn().mockResolvedValue({ success: true }),

      // Tasks
      getTasks: jest.fn().mockResolvedValue({ tasks: [], total: 0 }),
      getTask: jest.fn().mockResolvedValue({}),
      getTaskHistory: jest.fn().mockResolvedValue({ entries: [], total: 0 }),

      // Budget
      getBudget: jest
        .fn()
        .mockResolvedValue({ totalSpentUsd: 0, enabled: true }),
      getBudgetReport: jest
        .fn()
        .mockResolvedValue({ status: {}, taskSpending: [] }),

      // Agents & Audit
      getAgents: jest.fn().mockResolvedValue({ agents: [] }),
      getAudit: jest.fn().mockResolvedValue({ entries: [], total: 0 }),
      getAuditStatistics: jest
        .fn()
        .mockResolvedValue({ total: 0, successRate: 0 }),

      // Chat
      chat: jest
        .fn()
        .mockResolvedValue({ message: "Response", streaming: false }),
      executeCommand: jest.fn().mockResolvedValue({ success: true }),
      // EventEmitter methods
      on: jest.fn().mockReturnThis(),
      once: jest.fn().mockReturnThis(),
      emit: jest.fn().mockReturnValue(true),
      off: jest.fn().mockReturnThis(),
      addListener: jest.fn().mockReturnThis(),
      removeListener: jest.fn().mockReturnThis(),
      removeAllListeners: jest.fn().mockReturnThis(),
      setMaxListeners: jest.fn().mockReturnThis(),
      getMaxListeners: jest.fn().mockReturnValue(10),
      listeners: jest.fn().mockReturnValue([]),
      rawListeners: jest.fn().mockReturnValue([]),
      listenerCount: jest.fn().mockReturnValue(0),
      prependListener: jest.fn().mockReturnThis(),
      prependOnceListener: jest.fn().mockReturnThis(),
      eventNames: jest.fn().mockReturnValue([]),
    }) as unknown as jest.Mocked<OrchestratorClientService>;

/**
 * Provider configuration for test modules
 */
export const MockOrchestratorClientProvider = {
  provide: OrchestratorClientService,
  useFactory: createMockOrchestratorClient,
};

/**
 * Mock responses for common scenarios
 */
export const MockResponses = {
  // Health
  healthyResponse: { status: "healthy" },
  unhealthyResponse: { status: "unhealthy" },

  // Projects
  projectListResponse: [
    {
      name: "test-project",
      path: "/projects/test-project",
      created_at: "2024-01-01T00:00:00Z",
      current_phase: 1,
      has_documents: true,
      has_product_spec: true,
      has_claude_md: true,
      has_gemini_md: true,
      has_cursor_rules: false,
    },
    {
      name: "another-project",
      path: "/projects/another-project",
      created_at: "2024-01-02T00:00:00Z",
      current_phase: 0,
      has_documents: false,
      has_product_spec: false,
      has_claude_md: false,
      has_gemini_md: false,
      has_cursor_rules: false,
    },
  ],

  projectStatusResponse: {
    name: "test-project",
    path: "/projects/test-project",
    config: { name: "test-project", version: "1.0.0" },
    state: { phase: 1, status: "in_progress" },
    files: {
      "Docs/": true,
      "Docs/PRODUCT.md": true,
      "CLAUDE.md": true,
      "GEMINI.md": true,
      ".cursor/rules": false,
    },
    phases: {
      "1": { status: "completed", output: {} },
      "2": { status: "in_progress", output: {} },
    },
  },

  initProjectSuccessResponse: {
    success: true,
    project_dir: "/projects/new-project",
    message: "Project initialized successfully",
  },

  initProjectErrorResponse: {
    success: false,
    error: "Project already exists",
  },

  deleteProjectResponse: {
    message: "Project deleted successfully",
  },

  // Workflow
  workflowNotStartedResponse: {
    mode: "langgraph",
    status: "not_started",
    project: "test-project",
    phaseStatus: {},
  },

  workflowInProgressResponse: {
    mode: "langgraph",
    status: "in_progress",
    project: "test-project",
    current_phase: 2,
    phaseStatus: {
      "1": "completed",
      "2": "in_progress",
      "3": "pending",
      "4": "pending",
      "5": "pending",
    },
  },

  workflowPausedResponse: {
    mode: "langgraph",
    status: "paused",
    project: "test-project",
    current_phase: 3,
    phaseStatus: {
      "1": "completed",
      "2": "completed",
      "3": "in_progress",
    },
    pending_interrupt: {
      type: "escalation",
      message: "Human input required",
      options: ["approve", "reject"],
    },
  },

  workflowCompletedResponse: {
    mode: "langgraph",
    status: "completed",
    project: "test-project",
    current_phase: 5,
    phaseStatus: {
      "1": "completed",
      "2": "completed",
      "3": "completed",
      "4": "completed",
      "5": "completed",
    },
  },

  workflowHealthyResponse: {
    status: "healthy",
    project: "test-project",
    current_phase: 2,
    phaseStatus: "in_progress",
    iteration_count: 3,
    last_updated: "2024-01-01T12:00:00Z",
    agents: { claude: true, cursor: true, gemini: true },
    langgraph_enabled: true,
    has_context: true,
    total_commits: 5,
  },

  workflowDegradedResponse: {
    status: "degraded",
    project: "test-project",
    agents: { claude: true, cursor: false, gemini: true },
    langgraph_enabled: true,
  },

  workflowGraphResponse: {
    nodes: [
      { id: "planning", label: "Planning", status: "completed" },
      { id: "validation", label: "Validation", status: "in_progress" },
      { id: "implementation", label: "Implementation", status: "pending" },
      { id: "verification", label: "Verification", status: "pending" },
      { id: "completion", label: "Completion", status: "pending" },
    ],
    edges: [
      { source: "planning", target: "validation" },
      { source: "validation", target: "implementation" },
      { source: "implementation", target: "verification" },
      { source: "verification", target: "completion" },
    ],
  },

  startWorkflowSuccessResponse: {
    success: true,
    mode: "langgraph",
    paused: false,
    message: "Workflow started successfully",
    results: {},
  },

  startWorkflowPausedResponse: {
    success: true,
    mode: "langgraph",
    paused: true,
    message: "Workflow paused for human input",
    results: {
      pending_interrupt: { type: "escalation" },
    },
  },

  rollbackSuccessResponse: {
    success: true,
    rolled_back_to: "checkpoint_phase_2",
    current_phase: 2,
    message: "Rolled back to phase 2",
  },

  // Tasks
  taskListResponse: {
    tasks: [
      {
        id: "T1",
        title: "Implement user authentication",
        description: "Add login and registration",
        status: "completed",
        priority: 1,
        dependencies: [],
        files_to_create: ["src/auth/auth.service.ts"],
        files_to_modify: ["src/app.module.ts"],
        acceptance_criteria: ["Users can login", "Users can register"],
        complexity_score: 5.5,
        created_at: "2024-01-01T00:00:00Z",
        started_at: "2024-01-01T01:00:00Z",
        completed_at: "2024-01-01T02:00:00Z",
      },
      {
        id: "T2",
        title: "Add API endpoints",
        description: "Create REST API",
        status: "in_progress",
        priority: 2,
        dependencies: ["T1"],
        files_to_create: ["src/api/"],
        files_to_modify: [],
        acceptance_criteria: ["GET /users works", "POST /users works"],
        complexity_score: 3.2,
        created_at: "2024-01-01T00:00:00Z",
        started_at: "2024-01-01T02:30:00Z",
      },
      {
        id: "T3",
        title: "Write tests",
        status: "pending",
        priority: 3,
        dependencies: ["T2"],
        files_to_create: ["tests/"],
        files_to_modify: [],
        acceptance_criteria: ["80% coverage"],
        complexity_score: 2.0,
        created_at: "2024-01-01T00:00:00Z",
      },
    ],
    total: 3,
    completed: 1,
    in_progress: 1,
    pending: 1,
    failed: 0,
  },

  taskDetailResponse: {
    id: "T1",
    title: "Implement user authentication",
    description: "Add login and registration functionality",
    status: "completed",
    priority: 1,
    dependencies: [],
    files_to_create: [
      "src/auth/auth.service.ts",
      "src/auth/auth.controller.ts",
    ],
    files_to_modify: ["src/app.module.ts"],
    acceptance_criteria: [
      "Users can login with email/password",
      "Users can register with email/password",
      "JWT tokens are issued on login",
    ],
    complexity_score: 5.5,
    created_at: "2024-01-01T00:00:00Z",
    started_at: "2024-01-01T01:00:00Z",
    completed_at: "2024-01-01T02:00:00Z",
  },

  taskHistoryResponse: {
    entries: [
      {
        id: "entry-1",
        agent: "claude",
        task_id: "T1",
        session_id: "session-1",
        status: "success",
        duration_seconds: 120,
        cost_usd: 0.05,
        timestamp: "2024-01-01T01:30:00Z",
      },
      {
        id: "entry-2",
        agent: "cursor",
        task_id: "T1",
        session_id: "session-1",
        status: "success",
        duration_seconds: 30,
        cost_usd: 0.02,
        timestamp: "2024-01-01T01:45:00Z",
      },
    ],
    total: 2,
  },

  // Budget
  budgetStatusResponse: {
    total_spent_usd: 1.25,
    project_budget_usd: 10.0,
    project_remaining_usd: 8.75,
    project_used_percent: 12.5,
    task_count: 3,
    record_count: 15,
    task_spent: {
      T1: 0.75,
      T2: 0.5,
    },
    updated_at: "2024-01-01T12:00:00Z",
    enabled: true,
  },

  budgetReportResponse: {
    status: {
      totalSpentUsd: 1.25,
      projectBudgetUsd: 10.0,
      enabled: true,
      taskCount: 3,
      recordCount: 15,
      taskSpent: {
        T1: 0.75,
        T2: 0.5,
      },
    },
    taskSpending: [
      {
        taskId: "T1",
        spentUsd: 0.75,
        budgetUsd: 2.0,
        remainingUsd: 1.25,
        usedPercent: 37.5,
      },
      {
        taskId: "T2",
        spentUsd: 0.5,
        budgetUsd: 2.0,
        remainingUsd: 1.5,
        usedPercent: 25.0,
      },
    ],
  },

  // Agents
  agentsResponse: {
    agents: [
      {
        agent: "claude",
        available: true,
        lastInvocation: "2024-01-01T12:00:00Z",
        totalInvocations: 25,
        successRate: 0.92,
        avgDurationSeconds: 45.5,
        totalCostUsd: 1.25,
      },
      {
        agent: "cursor",
        available: true,
        lastInvocation: "2024-01-01T11:30:00Z",
        totalInvocations: 15,
        successRate: 0.87,
        avgDurationSeconds: 30.2,
        totalCostUsd: 0.45,
      },
      {
        agent: "gemini",
        available: true,
        lastInvocation: "2024-01-01T11:00:00Z",
        totalInvocations: 10,
        successRate: 0.9,
        avgDurationSeconds: 25.0,
        totalCostUsd: 0.15,
      },
    ],
  },

  auditEntriesResponse: {
    entries: [
      {
        id: "audit-1",
        agent: "claude",
        task_id: "T1",
        session_id: "session-1",
        prompt_hash: "abc123",
        prompt_length: 1500,
        command_args: ["-p", "Implement feature"],
        exit_code: 0,
        status: "success",
        duration_seconds: 120,
        output_length: 5000,
        error_length: 0,
        parsed_output_type: "json",
        cost_usd: 0.05,
        model: "claude-3-sonnet",
        metadata: {},
        timestamp: "2024-01-01T12:00:00Z",
      },
    ],
    total: 1,
  },

  auditStatisticsResponse: {
    total: 50,
    successCount: 45,
    failedCount: 3,
    timeoutCount: 2,
    successRate: 0.9,
    totalCostUsd: 2.5,
    totalDurationSeconds: 3600,
    avgDurationSeconds: 72.0,
    byAgent: { claude: 25, cursor: 15, gemini: 10 },
    byStatus: { success: 45, failed: 3, timeout: 2 },
  },

  // Chat
  chatResponse: {
    message:
      "I understand you want to implement the feature. Let me help you with that.",
    streaming: false,
  },

  commandSuccessResponse: {
    success: true,
    output: "Command executed successfully",
  },

  commandErrorResponse: {
    success: false,
    error: "Unknown command",
  },

  // Errors
  projectNotFoundError: {
    detail: "Project not found: nonexistent-project",
  },

  workflowNotStartedError: {
    detail: "Workflow has not been started",
  },

  invalidPhaseError: {
    detail: "Invalid phase number: 6. Must be between 1 and 5",
  },
};
