# Task Lifecycle

This document describes the lifecycle of tasks in the orchestration system, including state transitions, dependency resolution, and the incremental execution loop.

## Overview

Tasks are the atomic units of work in the implementation phase. The workflow breaks down the implementation plan into individual tasks, executes them one-by-one (or in parallel for independent tasks), and verifies each before proceeding.

## Task Data Model

```typescript
interface Task {
  // Identity
  id: string;              // e.g., "T1", "T2-a" (after split)
  title: string;           // Max 80 chars
  user_story: string;      // "As a... I want... So that..."

  // Scope
  acceptance_criteria: string[];  // Max 5 per task
  files_to_create: string[];      // Max 3 per task
  files_to_modify: string[];      // Max 5 per task
  test_files: string[];

  // Relationships
  dependencies: string[];   // Task IDs this depends on
  milestone_id: string;     // Parent milestone

  // Execution
  status: TaskStatus;
  priority: "critical" | "high" | "medium" | "low";
  estimated_complexity: "low" | "medium" | "high";
  attempts: number;         // Current attempt count
  max_attempts: number;     // Default: 3

  // Results
  implementation_notes: string;
  error: string | null;
  linear_issue_id: string | null;  // Optional Linear integration
}
```

## Task Status State Machine

```
                    ┌──────────────────────────────────────┐
                    │                                      │
                    ▼                                      │
┌─────────┐    ┌───────────┐    ┌───────────┐    ┌────────┴──┐
│ PENDING │───▶│IN_PROGRESS│───▶│ COMPLETED │    │   RETRY   │
└─────────┘    └───────────┘    └───────────┘    └───────────┘
     │              │                                  ▲
     │              │                                  │
     │              ▼                                  │
     │         ┌─────────┐                             │
     │         │ FAILED  │─────────────────────────────┘
     │         └─────────┘        (if attempts < max)
     │              │
     │              ▼ (if attempts >= max)
     │         [ESCALATE]
     │
     ▼
┌─────────┐
│ BLOCKED │ (deps not met)
└─────────┘
```

### Status Definitions

| Status | Meaning |
|--------|---------|
| `pending` | Task not yet started, waiting for selection |
| `in_progress` | Task currently being implemented |
| `completed` | Task successfully completed and verified |
| `failed` | Task failed after max retry attempts |
| `blocked` | Task dependencies not yet satisfied |

## Task Granularity

Tasks are enforced to be small and focused using multi-dimensional complexity assessment. Research shows file counts alone are insufficient - a task modifying 3 tightly coupled files may be harder than one modifying 10 isolated files.

### Complexity Triangle Principle

Tasks must satisfy multiple constraints simultaneously:
- **File scope** - Number of files touched
- **Cross-file dependencies** - Architectural coupling between files
- **Semantic complexity** - Algorithm difficulty, integration complexity
- **Token budget** - Estimated context consumption
- **Time budget** - Estimated execution time

### Complexity Scoring (0-13 Scale)

Tasks are evaluated using a composite complexity score:

| Component | Points | Description |
|-----------|--------|-------------|
| `file_scope` | 0-5 | 0.5 points per file, capped at 5 |
| `cross_file_deps` | 0-2 | Higher if files span multiple directories/layers |
| `semantic_complexity` | 0-3 | Based on complexity keywords (algorithm, async, etc.) |
| `requirement_uncertainty` | 0-2 | Vague language, unclear criteria |
| `token_penalty` | 0-1 | If estimated tokens exceed budget |

**Complexity Levels**:
| Total Score | Level | Action |
|-------------|-------|--------|
| 0-4 | LOW | Safe for autonomous execution |
| 5-7 | MEDIUM | Requires monitoring |
| 8-10 | HIGH | Consider decomposition |
| 11-13 | CRITICAL | Must decompose |

### Soft Limits (Guidance)

File limits generate warnings but don't force splits - complexity score is the primary decision factor:

| Guidance | Default | Purpose |
|----------|---------|---------|
| `max_files_to_create` | 5 | Context guidance |
| `max_files_to_modify` | 8 | Change scope guidance |
| `max_acceptance_criteria` | 7 | Scope clarity guidance |
| `max_input_tokens` | 6,000 | Token budget (4K-8K range) |
| `max_time_minutes` | 5 | Time budget (2-5 min range) |
| `complexity_threshold` | 5.0 | Auto-split trigger |

### Auto-Split Strategies

When complexity score exceeds threshold, the system selects a split strategy based on the dominant complexity factor:

**1. File Strategy** (dominant: high file_scope)
- Groups files by directory
- Keeps related files together
- Best for large file counts in few directories

**2. Layer Strategy** (dominant: high cross_file_deps)
- Separates by architectural layer (data, business, presentation)
- Reduces coupling between tasks
- Best for cross-cutting changes

**3. Criteria Strategy** (dominant: high semantic complexity/uncertainty)
- Splits by acceptance criteria
- Creates focused, clear sub-tasks
- Best for unclear or complex requirements

**Example**:
```
Original Task T1 (complexity: 8.5 - HIGH):
  file_scope: 3.0, cross_file_deps: 2.0, semantic: 2.5, uncertainty: 1.0
  Strategy selected: LAYERS (dominant: cross_file_deps)

After Split:
  T1-a: data layer files, criteria=[C1, C3], deps=[]
  T1-b: business layer files, criteria=[C2], deps=[T1-a]
  T1-c: presentation layer files, criteria=[C4], deps=[T1-b]
```

### Configuration

Override defaults in `.project-config.json`:

```json
{
  "task_size_limits": {
    "max_files_to_create": 5,
    "max_files_to_modify": 8,
    "max_criteria_per_task": 7,
    "max_input_tokens": 6000,
    "max_time_minutes": 5,
    "complexity_threshold": 5.0,
    "auto_split": true
  }
}
```

## Dependency Resolution

Tasks execute in dependency order. A task is **available** when:
- Status is `pending` (not completed, failed, or blocked)
- All tasks in `dependencies[]` are in `completed_task_ids`

### Dependency Types

1. **Explicit dependencies** - Defined in plan (e.g., `T2.dependencies = ["T1"]`)
2. **File-based dependencies** - Auto-assigned when task modifies files another task creates
3. **Split dependencies** - Auto-assigned between split task segments

### Resolution Algorithm

```python
def get_available_tasks(state):
    completed = set(state["completed_task_ids"])
    available = []

    for task in state["tasks"]:
        if task["id"] in completed:
            continue
        if task["status"] in [COMPLETED, FAILED]:
            continue

        deps_met = all(dep in completed for dep in task["dependencies"])
        if deps_met:
            available.append(task)

    return available
```

### Deadlock Detection

The system detects deadlocks (circular dependencies) during task breakdown:

```python
def detect_circular_dependencies(tasks):
    # DFS to find cycles in dependency graph
    # Returns list of cycles found
```

If cycles are detected, the workflow escalates to human for resolution.

## Task Loop Execution

```
task_breakdown → select_task → implement_task → verify_task
                     ↑              ↓
                     └──── LOOP ────┘
```

### 1. Task Breakdown

**Node**: `task_breakdown_node`

Converts the implementation plan into tasks:
- Parses PRODUCT.md acceptance criteria
- Extracts tasks from plan phases
- Validates task granularity (auto-splits if needed)
- Assigns file-based dependencies
- Detects circular dependencies
- Creates milestones for grouping
- Optionally syncs to Linear

### 2. Task Selection

**Node**: `select_task_node`

Selects the next task(s) to implement:

1. Filter to available tasks (deps met, not completed/failed)
2. Sort by priority (critical > high > medium > low)
3. Sort by milestone order
4. Select single task OR batch for parallel execution

**Parallel Selection**: If parallel workers configured, selects multiple independent tasks (non-overlapping files).

### 3. Task Implementation

**Node**: `implement_task_node`

Executes the selected task:

1. Build scoped prompt with:
   - Task description and acceptance criteria
   - Files to create/modify (explicit list)
   - Test files to create/update
   - Context from completed tasks

2. Spawn worker Claude:
   ```bash
   claude -p "<scoped-prompt>" --output-format json
   ```

3. Parse result and update task status

4. If using Ralph loop (TDD):
   - Iterate until tests pass
   - Fresh context each iteration
   - Completion signal: `<promise>DONE</promise>`

### 4. Task Verification

**Node**: `verify_task_node`

Verifies the task implementation:

1. Check files created exist
2. Run tests for task's test_files
3. Parse test results
4. Update task status:
   - Success → `completed`, add to `completed_task_ids`
   - Failure with retries → `pending`, increment `attempts`
   - Failure at max retries → `failed`, add to `failed_task_ids`

### 5. Loop Decision

**Router**: `verify_task_router`

Determines next action:
- If available tasks remain → `select_task` (LOOP)
- If all tasks completed → `build_verification` (EXIT)
- If no available tasks but incomplete remain → `human_escalation` (DEADLOCK)
- If task failed but retries remain → `implement_task` (RETRY)

## Parallel Execution

When `parallel_workers > 1` in config, independent tasks can run simultaneously.

### Independence Criteria

Tasks are independent if they have no overlapping files:
```python
def are_independent(task_a, task_b):
    files_a = set(task_a.files_to_create + task_a.files_to_modify)
    files_b = set(task_b.files_to_create + task_b.files_to_modify)
    return files_a.isdisjoint(files_b)
```

### Git Worktree Execution

Parallel tasks use isolated git worktrees:

1. Create worktree for each worker
2. Workers execute in isolation
3. Cherry-pick results back to main branch
4. Clean up worktrees

### Parallel Routers

- `select_task_router` → `implement_tasks_parallel` when batch selected
- `implement_tasks_parallel_router` → `verify_tasks_parallel`
- `verify_tasks_parallel_router` → `select_task` (loop back)

## Error Handling

### Retry Strategy

Failed tasks are retried with:
- Incremented attempt counter
- Error context from previous attempt
- Enhanced prompt with failure analysis

### Max Retries Exceeded

When `attempts >= max_attempts`:
- Task status → `failed`
- Task added to `failed_task_ids`
- Workflow escalates to human

### Recovery Options

After human escalation, options include:
- Fix manually and continue
- Skip task (mark completed externally)
- Abort workflow
- Reset task attempts and retry

## Milestones

Tasks are grouped into milestones for tracking and organization.

```typescript
interface Milestone {
  id: string;           // e.g., "M1"
  name: string;         // e.g., "Core Features"
  description: string;
  task_ids: string[];   // Tasks in this milestone
  status: TaskStatus;   // Derived from task statuses
}
```

Milestone status is derived:
- `completed` if all tasks completed
- `in_progress` if any task in progress
- `pending` if all tasks pending
- `failed` if any task failed

## Linear Integration

Tasks can optionally sync to Linear for project management:

```json
{
  "integrations": {
    "linear": {
      "enabled": true,
      "team_id": "TEAM123",
      "create_project": true
    }
  }
}
```

When enabled:
- Tasks create Linear issues
- Status changes sync to Linear workflow states
- Issue IDs stored in `task.linear_issue_id`

## Monitoring Task Progress

### State Fields

Key state fields for monitoring:

| Field | Type | Description |
|-------|------|-------------|
| `tasks` | Task[] | All tasks |
| `milestones` | Milestone[] | Task groupings |
| `current_task_id` | string | Currently executing task |
| `current_task_ids` | string[] | Parallel batch |
| `completed_task_ids` | string[] | Completed tasks |
| `failed_task_ids` | string[] | Failed tasks |
| `in_flight_task_ids` | string[] | Executing (parallel) |

### Task Summary

```python
def get_task_summary(state):
    return {
        "total": len(state["tasks"]),
        "pending": [t.id for t in tasks if t.status == "pending"],
        "in_progress": [t.id for t in tasks if t.status == "in_progress"],
        "completed": state["completed_task_ids"],
        "failed": state["failed_task_ids"],
        "current_task_id": state.get("current_task_id"),
    }
```

### Workflow Summary

The workflow summary includes task progress:

```python
summary = {
    "tasks": {
        "total": 10,
        "completed": 7,
        "pending": 2,
        "failed": 1,
        "progress": "70%"
    }
}
```
