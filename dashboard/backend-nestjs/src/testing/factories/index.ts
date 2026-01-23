import {
  WorkflowStatus,
  PhaseStatus,
  TaskStatus,
  AgentType,
} from "../../common/enums";

/**
 * Factory utilities for generating test data
 */

let idCounter = 0;
const generateId = (prefix = "test") => `${prefix}-${++idCounter}`;

export const resetIdCounter = () => {
  idCounter = 0;
};

// ==================== Project Factories ====================

export interface ProjectSummaryData {
  name: string;
  path: string;
  createdAt?: string;
  currentPhase: number;
  hasDocuments: boolean;
  hasProductSpec: boolean;
  hasClaudeMd: boolean;
  hasGeminiMd: boolean;
  hasCursorRules: boolean;
}

export const createProjectSummary = (
  overrides: Partial<ProjectSummaryData> = {},
): ProjectSummaryData => ({
  name: overrides.name ?? `project-${generateId()}`,
  path: overrides.path ?? `/projects/${overrides.name ?? "test-project"}`,
  createdAt: overrides.createdAt ?? new Date().toISOString(),
  currentPhase: overrides.currentPhase ?? 0,
  hasDocuments: overrides.hasDocuments ?? false,
  hasProductSpec: overrides.hasProductSpec ?? false,
  hasClaudeMd: overrides.hasClaudeMd ?? false,
  hasGeminiMd: overrides.hasGeminiMd ?? false,
  hasCursorRules: overrides.hasCursorRules ?? false,
});

export const createProjectSummaryList = (
  count: number,
  overrides: Partial<ProjectSummaryData> = {},
): ProjectSummaryData[] =>
  Array.from({ length: count }, (_, i) =>
    createProjectSummary({ ...overrides, name: `project-${i + 1}` }),
  );

export interface ProjectStatusData {
  name: string;
  path: string;
  config?: Record<string, unknown>;
  state?: Record<string, unknown>;
  files: Record<string, boolean>;
  phases: Record<string, Record<string, unknown>>;
}

export const createProjectStatus = (
  overrides: Partial<ProjectStatusData> = {},
): ProjectStatusData => ({
  name: overrides.name ?? "test-project",
  path: overrides.path ?? "/projects/test-project",
  config: overrides.config ?? { name: "test-project", version: "1.0.0" },
  state: overrides.state ?? { phase: 1, status: "in_progress" },
  files: overrides.files ?? {
    "Docs/": true,
    "Docs/PRODUCT.md": true,
    "CLAUDE.md": false,
    "GEMINI.md": false,
    ".cursor/rules": false,
  },
  phases: overrides.phases ?? {},
});

// ==================== Workflow Factories ====================

export interface WorkflowStatusData {
  mode?: string;
  status: WorkflowStatus;
  project?: string;
  currentPhase?: number;
  phaseStatus?: Record<string, string>;
  pendingInterrupt?: Record<string, unknown>;
  message?: string;
}

export const createWorkflowStatus = (
  overrides: Partial<WorkflowStatusData> = {},
): WorkflowStatusData => ({
  mode: overrides.mode ?? "langgraph",
  status: overrides.status ?? WorkflowStatus.NOT_STARTED,
  project: overrides.project ?? "test-project",
  currentPhase: overrides.currentPhase,
  phaseStatus: overrides.phaseStatus ?? {},
  pendingInterrupt: overrides.pendingInterrupt,
  message: overrides.message,
});

export const createWorkflowInProgress = (
  phase: number = 2,
  project: string = "test-project",
): WorkflowStatusData => ({
  mode: "langgraph",
  status: WorkflowStatus.IN_PROGRESS,
  project,
  currentPhase: phase,
  phaseStatus: Object.fromEntries(
    Array.from({ length: 5 }, (_, i) => [
      String(i + 1),
      i + 1 < phase ? "completed" : i + 1 === phase ? "in_progress" : "pending",
    ]),
  ),
});

export const createWorkflowPaused = (
  phase: number = 3,
  interruptType: string = "escalation",
): WorkflowStatusData => ({
  mode: "langgraph",
  status: WorkflowStatus.PAUSED,
  project: "test-project",
  currentPhase: phase,
  phaseStatus: Object.fromEntries(
    Array.from({ length: 5 }, (_, i) => [
      String(i + 1),
      i + 1 < phase ? "completed" : i + 1 === phase ? "in_progress" : "pending",
    ]),
  ),
  pendingInterrupt: {
    type: interruptType,
    message: "Human input required",
    options: ["approve", "reject"],
  },
});

export const createWorkflowCompleted = (
  project: string = "test-project",
): WorkflowStatusData => ({
  mode: "langgraph",
  status: WorkflowStatus.COMPLETED,
  project,
  currentPhase: 5,
  phaseStatus: {
    "1": "completed",
    "2": "completed",
    "3": "completed",
    "4": "completed",
    "5": "completed",
  },
  message: "Workflow completed successfully",
});

export interface WorkflowHealthData {
  status: string;
  project?: string;
  currentPhase?: number;
  phaseStatus?: string;
  iterationCount?: number;
  lastUpdated?: string;
  agents?: Record<string, boolean>;
  langgraphEnabled?: boolean;
  hasContext?: boolean;
  totalCommits?: number;
}

export const createWorkflowHealth = (
  overrides: Partial<WorkflowHealthData> = {},
): WorkflowHealthData => ({
  status: overrides.status ?? "healthy",
  project: overrides.project ?? "test-project",
  currentPhase: overrides.currentPhase ?? 1,
  phaseStatus: overrides.phaseStatus ?? "in_progress",
  iterationCount: overrides.iterationCount ?? 0,
  lastUpdated: overrides.lastUpdated ?? new Date().toISOString(),
  agents: overrides.agents ?? { claude: true, cursor: true, gemini: true },
  langgraphEnabled: overrides.langgraphEnabled ?? true,
  hasContext: overrides.hasContext ?? true,
  totalCommits: overrides.totalCommits ?? 0,
});

export interface WorkflowStartResponseData {
  success: boolean;
  mode?: string;
  paused?: boolean;
  message?: string;
  error?: string;
  results?: Record<string, unknown>;
}

export const createWorkflowStartResponse = (
  success: boolean = true,
  overrides: Partial<WorkflowStartResponseData> = {},
): WorkflowStartResponseData => ({
  success,
  mode: overrides.mode ?? "langgraph",
  paused: overrides.paused ?? false,
  message: overrides.message ?? (success ? "Workflow started" : undefined),
  error: overrides.error ?? (success ? undefined : "Failed to start workflow"),
  results: overrides.results,
});

// ==================== Task Factories ====================

export interface TaskData {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: number;
  dependencies: string[];
  filesToCreate: string[];
  filesToModify: string[];
  acceptanceCriteria: string[];
  complexityScore?: number;
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
  error?: string;
}

export const createTask = (overrides: Partial<TaskData> = {}): TaskData => ({
  id: overrides.id ?? generateId("T"),
  title: overrides.title ?? "Test Task",
  description: overrides.description,
  status: overrides.status ?? TaskStatus.PENDING,
  priority: overrides.priority ?? 0,
  dependencies: overrides.dependencies ?? [],
  filesToCreate: overrides.filesToCreate ?? [],
  filesToModify: overrides.filesToModify ?? [],
  acceptanceCriteria: overrides.acceptanceCriteria ?? [],
  complexityScore: overrides.complexityScore,
  createdAt: overrides.createdAt ?? new Date().toISOString(),
  startedAt: overrides.startedAt,
  completedAt: overrides.completedAt,
  error: overrides.error,
});

export const createTaskList = (
  count: number,
  statusDistribution?: Partial<Record<TaskStatus, number>>,
): TaskData[] => {
  const tasks: TaskData[] = [];
  const statuses = Object.values(TaskStatus);

  for (let i = 0; i < count; i++) {
    const status = statusDistribution
      ? (Object.entries(statusDistribution).find(
          ([_, targetCount], idx) =>
            tasks.filter(
              (t) => t.status === Object.keys(statusDistribution)[idx],
            ).length < targetCount,
        )?.[0] as TaskStatus) ?? TaskStatus.PENDING
      : statuses[i % statuses.length];

    tasks.push(
      createTask({
        id: `T${i + 1}`,
        title: `Task ${i + 1}`,
        status,
        priority: i + 1,
        dependencies: i > 0 ? [`T${i}`] : [],
        filesToCreate: [],
        filesToModify: [],
        acceptanceCriteria: [],
      }),
    );
  }

  return tasks;
};

export interface TaskListResponseData {
  tasks: TaskData[];
  total: number;
  completed: number;
  inProgress: number;
  pending: number;
  failed: number;
}

export const createTaskListResponse = (
  tasks: TaskData[] = [],
): TaskListResponseData => ({
  tasks,
  total: tasks.length,
  completed: tasks.filter((t) => t.status === TaskStatus.COMPLETED).length,
  inProgress: tasks.filter((t) => t.status === TaskStatus.IN_PROGRESS).length,
  pending: tasks.filter((t) => t.status === TaskStatus.PENDING).length,
  failed: tasks.filter((t) => t.status === TaskStatus.FAILED).length,
});

// ==================== Agent Factories ====================

export interface AgentStatusData {
  agent: AgentType;
  available: boolean;
  lastInvocation?: string;
  totalInvocations: number;
  successRate: number;
  avgDurationSeconds: number;
  totalCostUsd: number;
}

export const createAgentStatus = (
  agent: AgentType,
  overrides: Partial<AgentStatusData> = {},
): AgentStatusData => ({
  agent,
  available: overrides.available ?? true,
  lastInvocation: overrides.lastInvocation ?? new Date().toISOString(),
  totalInvocations: overrides.totalInvocations ?? 0,
  successRate: overrides.successRate ?? 1.0,
  avgDurationSeconds: overrides.avgDurationSeconds ?? 0,
  totalCostUsd: overrides.totalCostUsd ?? 0,
  // DTO fields might be different (camelCase vs snake_case or missing)
  // Checking AgentStatusDto usually expects totalInvocations etc.
});

export const createAllAgentStatuses = (
  overrides: Partial<Record<AgentType, Partial<AgentStatusData>>> = {},
): AgentStatusData[] => [
  createAgentStatus(AgentType.CLAUDE, overrides[AgentType.CLAUDE]),
  createAgentStatus(AgentType.CURSOR, overrides[AgentType.CURSOR]),
  createAgentStatus(AgentType.GEMINI, overrides[AgentType.GEMINI]),
];

export interface AuditEntryData {
  id: string;
  agent: string;
  taskId: string;
  sessionId?: string;
  promptHash?: string;
  promptLength?: number;
  commandArgs?: string[];
  exitCode?: number;
  status: string;
  durationSeconds?: number;
  outputLength?: number;
  errorLength?: number;
  parsedOutputType?: string;
  costUsd?: number;
  model?: string;
  metadata?: Record<string, unknown>;
  timestamp?: string;
}

export const createAuditEntry = (
  overrides: Partial<AuditEntryData> = {},
): AuditEntryData => ({
  id: overrides.id ?? generateId("audit"),
  agent: overrides.agent ?? "claude",
  taskId: overrides.taskId ?? "T1",
  sessionId: overrides.sessionId,
  promptHash: overrides.promptHash,
  promptLength: overrides.promptLength,
  commandArgs: overrides.commandArgs ?? [],
  exitCode: overrides.exitCode,
  status: overrides.status ?? "success",
  durationSeconds: overrides.durationSeconds,
  outputLength: overrides.outputLength,
  errorLength: overrides.errorLength,
  parsedOutputType: overrides.parsedOutputType,
  costUsd: overrides.costUsd,
  model: overrides.model,
  metadata: overrides.metadata ?? {},
  timestamp: overrides.timestamp ?? new Date().toISOString(),
});

export interface AuditStatisticsData {
  total: number;
  successCount: number;
  failedCount: number;
  timeoutCount: number;
  successRate: number;
  totalCostUsd: number;
  totalDurationSeconds: number;
  avgDurationSeconds: number;
  byAgent: Record<string, number>;
  byStatus: Record<string, number>;
}

export const createAuditStatistics = (
  overrides: Partial<AuditStatisticsData> = {},
): AuditStatisticsData => ({
  total: overrides.total ?? 0,
  successCount: overrides.successCount ?? 0,
  failedCount: overrides.failedCount ?? 0,
  timeoutCount: overrides.timeoutCount ?? 0,
  successRate: overrides.successRate ?? 0,
  totalCostUsd: overrides.totalCostUsd ?? 0,
  totalDurationSeconds: overrides.totalDurationSeconds ?? 0,
  avgDurationSeconds: overrides.avgDurationSeconds ?? 0,
  byAgent: overrides.byAgent ?? {},
  byStatus: overrides.byStatus ?? {},
});

// ==================== Budget Factories ====================

export interface BudgetStatusData {
  totalSpentUsd: number;
  projectBudgetUsd?: number;
  projectRemainingUsd?: number;
  projectUsedPercent?: number;
  taskCount: number;
  recordCount: number;
  taskSpent: Record<string, number>;
  updatedAt?: string;
  enabled: boolean;
}

export const createBudgetStatus = (
  overrides: Partial<BudgetStatusData> = {},
): BudgetStatusData => ({
  totalSpentUsd: overrides.totalSpentUsd ?? 0,
  projectBudgetUsd: overrides.projectBudgetUsd,
  projectRemainingUsd: overrides.projectRemainingUsd,
  projectUsedPercent: overrides.projectUsedPercent,
  taskCount: overrides.taskCount ?? 0,
  recordCount: overrides.recordCount ?? 0,
  taskSpent: overrides.taskSpent ?? {},
  updatedAt: overrides.updatedAt ?? new Date().toISOString(),
  enabled: overrides.enabled ?? true,
});

export interface TaskSpendingData {
  taskId: string;
  spentUsd: number;
  budgetUsd?: number;
  remainingUsd?: number;
  usedPercent?: number;
}

export const createTaskSpending = (
  taskId: string,
  overrides: Partial<TaskSpendingData> = {},
): TaskSpendingData => ({
  taskId,
  spentUsd: overrides.spentUsd ?? 0,
  budgetUsd: overrides.budgetUsd,
  remainingUsd: overrides.remainingUsd,
  usedPercent: overrides.usedPercent,
});

// ==================== Chat Factories ====================

export interface ChatMessageData {
  role: string;
  content: string;
  timestamp?: string;
}

export const createChatMessage = (
  role: "user" | "assistant" | "system",
  content: string,
  timestamp?: string,
): ChatMessageData => ({
  role,
  content,
  timestamp: timestamp ?? new Date().toISOString(),
});

export interface ChatResponseData {
  message: string;
  streaming: boolean;
}

export const createChatResponse = (
  message: string,
  streaming: boolean = false,
): ChatResponseData => ({
  message,
  streaming,
});

export interface CommandResponseData {
  success: boolean;
  output?: string;
  error?: string;
}

export const createCommandResponse = (
  success: boolean,
  output?: string,
  error?: string,
): CommandResponseData => ({
  success,
  output: success ? output : undefined,
  error: success ? undefined : error,
});

// ==================== WebSocket Event Factories ====================

export interface WebSocketEventData {
  type: string;
  project: string;
  payload: Record<string, unknown>;
  timestamp?: string;
}

export const createWebSocketEvent = (
  type: string,
  project: string,
  payload: Record<string, unknown> = {},
): WebSocketEventData => ({
  type,
  project,
  payload,
  timestamp: new Date().toISOString(),
});

export const createStateChangeEvent = (
  project: string,
  newState: Record<string, unknown>,
): WebSocketEventData =>
  createWebSocketEvent("state_change", project, { state: newState });

export const createActionEvent = (
  project: string,
  action: string,
  details: Record<string, unknown> = {},
): WebSocketEventData =>
  createWebSocketEvent("action", project, { action, ...details });

export const createEscalationEvent = (
  project: string,
  message: string,
  options: string[] = ["approve", "reject"],
): WebSocketEventData =>
  createWebSocketEvent("escalation", project, { message, options });

// ==================== Export All ====================

export const factories = {
  // Project
  createProjectSummary,
  createProjectSummaryList,
  createProjectStatus,

  // Workflow
  createWorkflowStatus,
  createWorkflowInProgress,
  createWorkflowPaused,
  createWorkflowCompleted,
  createWorkflowHealth,
  createWorkflowStartResponse,

  // Task
  createTask,
  createTaskList,
  createTaskListResponse,

  // Agent
  createAgentStatus,
  createAllAgentStatuses,
  createAuditEntry,
  createAuditStatistics,

  // Budget
  createBudgetStatus,
  createTaskSpending,

  // Chat
  createChatMessage,
  createChatResponse,
  createCommandResponse,

  // WebSocket
  createWebSocketEvent,
  createStateChangeEvent,
  createActionEvent,
  createEscalationEvent,

  // Utils
  resetIdCounter,
};

export default factories;
