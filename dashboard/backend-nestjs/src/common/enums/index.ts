export enum WorkflowStatus {
  NOT_STARTED = "not_started",
  IN_PROGRESS = "in_progress",
  PAUSED = "paused",
  COMPLETED = "completed",
  FAILED = "failed",
}

export enum PhaseStatus {
  PENDING = "pending",
  IN_PROGRESS = "in_progress",
  COMPLETED = "completed",
  FAILED = "failed",
  SKIPPED = "skipped",
}

export enum TaskStatus {
  PENDING = "pending",
  IN_PROGRESS = "in_progress",
  COMPLETED = "completed",
  FAILED = "failed",
  BLOCKED = "blocked",
  SKIPPED = "skipped",
}

export enum AgentType {
  CLAUDE = "claude",
  CURSOR = "cursor",
  GEMINI = "gemini",
}

export enum WebSocketEventType {
  ACTION = "action",
  STATE_CHANGE = "state_change",
  ESCALATION = "escalation",
  CHAT = "chat",
  WORKFLOW_COMPLETE = "workflow_complete",
  WORKFLOW_ERROR = "workflow_error",
  PAUSE_REQUESTED = "pause_requested",
}
