/**
 * Type definitions for the Conductor Dashboard
 */

// Enums
export type WorkflowStatus =
  | "not_started"
  | "in_progress"
  | "paused"
  | "completed"
  | "failed";
export type PhaseStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "skipped";
export type TaskStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "blocked"
  | "skipped";
export type AgentType = "claude" | "cursor" | "gemini";

// Project types
export interface ProjectSummary {
  name: string;
  path: string;
  created_at?: string;
  current_phase: number;
  has_documents: boolean;
  has_product_spec: boolean;
  has_claude_md: boolean;
  has_gemini_md: boolean;
  has_cursor_rules: boolean;
  workflow_status?: string;
  last_activity?: string;
}

export interface ProjectStatus {
  name: string;
  path: string;
  config?: Record<string, unknown>;
  state?: Record<string, unknown>;
  files: Record<string, boolean>;
  phases: Record<string, { exists: boolean; has_output: boolean }>;
}

export interface FolderInfo {
  name: string;
  path: string;
  is_project: boolean;
  has_workflow: boolean;
  has_product_md: boolean;
}

// Workflow types
export interface WorkflowStatusResponse {
  mode: string;
  status: WorkflowStatus;
  project?: string;
  current_phase?: number;
  phase_status: Record<string, string>;
  pending_interrupt?: Record<string, unknown>;
  message?: string;
}

export interface WorkflowHealthResponse {
  status: string;
  project?: string;
  current_phase?: number;
  phase_status?: string;
  iteration_count: number;
  last_updated?: string;
  agents: Record<string, boolean>;
  langgraph_enabled: boolean;
  has_context: boolean;
  total_commits: number;
}

// Task types
export interface TaskInfo {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: number;
  dependencies: string[];
  files_to_create: string[];
  files_to_modify: string[];
  acceptance_criteria: string[];
  complexity_score?: number;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export interface TaskListResponse {
  tasks: TaskInfo[];
  total: number;
  completed: number;
  in_progress: number;
  pending: number;
  failed: number;
}

// Agent types
export interface AgentStatus {
  agent: AgentType;
  available: boolean;
  last_invocation?: string;
  total_invocations: number;
  success_rate: number;
  avg_duration_seconds: number;
  total_cost_usd: number;
}

export interface AgentStatusResponse {
  agents: AgentStatus[];
}

// Audit types
export interface AuditEntry {
  id: string;
  agent: string;
  task_id: string;
  session_id?: string;
  prompt_hash?: string;
  prompt_length?: number;
  command_args: string[];
  exit_code?: number;
  status: string;
  duration_seconds?: number;
  output_length?: number;
  error_length?: number;
  parsed_output_type?: string;
  cost_usd?: number;
  model?: string;
  metadata: Record<string, unknown>;
  timestamp?: string;
}

export interface AuditResponse {
  entries: AuditEntry[];
  total: number;
}

export interface AuditStatistics {
  total: number;
  success_count: number;
  failed_count: number;
  timeout_count: number;
  success_rate: number;
  total_cost_usd: number;
  total_duration_seconds: number;
  avg_duration_seconds: number;
  by_agent: Record<string, number>;
  by_status: Record<string, number>;
}

// Session types
export interface SessionInfo {
  session_id: string;
  task_id: string;
  agent: string;
  created_at: string;
  last_active?: string;
  iteration: number;
  active: boolean;
}

// Budget types
export interface BudgetStatus {
  total_spent_usd: number;
  project_budget_usd?: number;
  project_remaining_usd?: number;
  project_used_percent?: number;
  task_count: number;
  record_count: number;
  task_spent: Record<string, number>;
  updated_at?: string;
  enabled: boolean;
}

export interface TaskSpending {
  task_id: string;
  spent_usd: number;
  budget_usd?: number;
  remaining_usd?: number;
  used_percent?: number;
}

export interface BudgetReportResponse {
  status: BudgetStatus;
  task_spending: TaskSpending[];
}

// Feedback types
export interface FeedbackResponse {
  phase: number;
  agent: AgentType;
  status: string;
  score?: number;
  issues: Record<string, unknown>[];
  suggestions: string[];
  timestamp?: string;
}

export interface EscalationQuestion {
  id: string;
  question: string;
  options: string[];
  context?: string;
  created_at: string;
}

// Chat types
export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
}

export interface ChatRequest {
  message: string;
  project_name?: string;
  context?: Record<string, unknown>;
}

export interface ChatResponse {
  message: string;
  streaming: boolean;
}

// WebSocket types
export interface WebSocketEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

// API Error type
export interface ApiError {
  error: string;
  detail?: string;
  status_code: number;
}
