# Router Reference

This document provides a complete reference for all workflow routers in the orchestration system.

## Overview

Routers are functions that determine the next node in the workflow graph based on the current state. They implement the decision logic that controls workflow progression.

All routers follow this pattern:
- Input: `WorkflowState` dictionary
- Output: String literal representing the next node name

## Router Decision Matrix

### Summary Table

| Router | Input State | Outputs | Primary Decision Field |
|--------|-------------|---------|----------------------|
| `prerequisites_router` | Phase 0 complete | `planning`, `human_escalation`, `__end__` | `next_decision` |
| `planning_router` | Plan created | `cursor_validate`, `human_escalation`, `__end__` | `next_decision`, `plan` |
| `validation_router` | Validation results | `implementation`, `planning`, `human_escalation`, `__end__` | `next_decision` |
| `implementation_router` | Implementation result | `cursor_review`, `planning`, `human_escalation`, `__end__` | `next_decision` |
| `verification_router` | Review results | `completion`, `implementation`, `human_escalation`, `__end__` | `next_decision`, `errors` |
| `completion_router` | Final state | `__end__` | Always ends |

### Task Loop Routers

| Router | Input State | Outputs | Primary Decision Field |
|--------|-------------|---------|----------------------|
| `task_breakdown_router` | Tasks created | `select_task`, `human_escalation`, `__end__` | `next_decision`, `tasks` |
| `select_task_router` | Task selected | `implement_task`, `implement_tasks_parallel`, `build_verification`, `human_escalation` | `next_decision`, `current_task_id(s)` |
| `implement_task_router` | Task implemented | `verify_task`, `implement_task`, `human_escalation` | `next_decision` |
| `verify_task_router` | Task verified | `select_task`, `implement_task`, `human_escalation` | `next_decision`, task `attempts` |

---

## Phase Routers

### prerequisites_router

Routes after prerequisite checks (PRODUCT.md validation, environment checks).

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
next_decision == "continue" → planning
next_decision == "escalate" → human_escalation
next_decision == "abort" → __end__
phase_0.status == COMPLETED → planning
phase_0.status == FAILED → human_escalation
blocking errors exist → human_escalation
default → planning
```

**State Requirements**:
- `phase_status["0"]` - Phase 0 status
- `errors` - List of errors from prerequisite checks

---

### planning_router

Routes after the planning phase produces an implementation plan.

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
next_decision == "continue" → cursor_validate
next_decision == "escalate" → human_escalation
next_decision == "abort" → __end__
plan exists and has plan_name → cursor_validate
phase_1.status == COMPLETED → cursor_validate
phase_1.status == FAILED and max_attempts reached → human_escalation
default → human_escalation
```

**State Requirements**:
- `plan` - Generated implementation plan
- `phase_status["1"]` - Phase 1 status

**Note**: Routes to `cursor_validate` which triggers parallel fan-out to both Cursor and Gemini validators.

---

### validation_router

Routes after validation fan-in (merging Cursor and Gemini validation results).

**File**: `orchestrator/langgraph/routers/validation.py`

**Decision Logic**:
```
next_decision == "continue" → implementation
next_decision == "retry" → planning
next_decision == "escalate" → human_escalation
next_decision == "abort" → __end__
phase_2.status == COMPLETED → implementation
phase_2.status == FAILED and max_attempts reached → human_escalation
phase_2.status == FAILED and retries remaining → planning
default → human_escalation
```

**State Requirements**:
- `cursor_validation` - Cursor validation result
- `gemini_validation` - Gemini validation result
- `phase_status["2"]` - Phase 2 status

---

### implementation_router

Routes after the implementation phase completes.

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
next_decision == "continue" → cursor_review
next_decision == "retry" → planning
next_decision == "escalate" → human_escalation
next_decision == "abort" → __end__
phase_3.status == COMPLETED → cursor_review
phase_3.status == FAILED and max_attempts reached → human_escalation
phase_3.status == FAILED and retries remaining → planning
test_results.failed > 0 → planning
default → cursor_review
```

**State Requirements**:
- `implementation_result` - Implementation output
- `phase_status["3"]` - Phase 3 status

---

### verification_router

Routes after verification fan-in (merging Cursor and Gemini code reviews).

**File**: `orchestrator/langgraph/routers/verification.py`

**Decision Logic**:
```
# Check build errors first (run before parallel reviews)
build_errors exist and iteration_count >= 3 → human_escalation
build_errors exist → implementation

next_decision == "continue" → completion
next_decision == "retry" → implementation
next_decision == "escalate" → human_escalation
next_decision == "abort" → __end__
phase_4.status == COMPLETED → completion
phase_4.status == FAILED and max_attempts reached → human_escalation
phase_4.status == FAILED → implementation
default → human_escalation
```

**State Requirements**:
- `errors` - May contain `build_verification_failed` errors
- `cursor_review` - Cursor code review result
- `gemini_review` - Gemini architecture review result
- `phase_status["4"]` - Phase 4 status
- `iteration_count` - Number of implementation iterations

---

### completion_router

Routes after the completion phase. Always ends the workflow.

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
Always → __end__
```

---

## Task Loop Routers

### task_breakdown_router

Routes after task breakdown creates individual tasks from the plan.

**File**: `orchestrator/langgraph/routers/task.py`

**Decision Logic**:
```
next_decision == "continue" and tasks exist → select_task
next_decision == "continue" and no tasks → __end__
next_decision == "escalate" → human_escalation
next_decision == "abort" → __end__
tasks exist → select_task
default → __end__
```

**State Requirements**:
- `tasks` - List of created tasks
- `milestones` - List of milestones

---

### select_task_router

Routes after task selection to determine sequential vs parallel execution.

**File**: `orchestrator/langgraph/routers/task.py`

**Decision Logic**:
```
next_decision == "continue" and multiple tasks selected → implement_tasks_parallel
next_decision == "continue" and single task selected → implement_task
next_decision == "continue" and all tasks completed → build_verification
next_decision == "escalate" → human_escalation
multiple current_task_ids → implement_tasks_parallel
single current_task_id → implement_task
all_tasks_completed → build_verification
default → human_escalation
```

**State Requirements**:
- `current_task_id` - Single selected task (legacy)
- `current_task_ids` - Batch of selected tasks
- `tasks` - All tasks
- `completed_task_ids` - Completed task IDs

---

### implement_task_router

Routes after task implementation to verification or retry.

**File**: `orchestrator/langgraph/routers/task.py`

**Decision Logic**:
```
next_decision == "continue" → verify_task
next_decision == "retry" → implement_task
next_decision == "escalate" → human_escalation
current_task_id exists → verify_task
default → human_escalation
```

**State Requirements**:
- `current_task_id` - Task being implemented
- Task implementation result

---

### verify_task_router

Routes after task verification. This is the **key loop router**.

**File**: `orchestrator/langgraph/routers/task.py`

**Decision Logic**:
```
next_decision == "continue" and tasks available → select_task (LOOP)
next_decision == "retry" and retries remaining → implement_task
next_decision == "retry" and max retries → human_escalation
next_decision == "escalate" → human_escalation
task.status == COMPLETED and tasks available → select_task (LOOP)
task.status == FAILED → human_escalation
no current_task and tasks available → select_task
default → select_task or human_escalation (based on availability)
```

**Important**: This router includes deadlock detection via `_check_for_available_tasks_or_escalate()`.

**State Requirements**:
- `current_task_id` - Task just verified
- `tasks` - All tasks with status
- `completed_task_ids` - Completed task IDs

---

## Utility Routers

### human_escalation_router

Routes after human provides input during escalation.

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
next_decision == "continue" and current_phase <= 1 → planning
next_decision == "continue" and current_phase <= 3 → implementation
next_decision == "continue" and current_phase > 3 → completion
next_decision == "retry" and current_phase <= 2 → planning
next_decision == "retry" and current_phase > 2 → implementation
default → __end__
```

---

### build_verification_router

Routes after build verification (compile/lint checks).

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
next_decision == "continue" → cursor_review
next_decision == "retry" → implementation
next_decision == "escalate" → human_escalation
next_decision == "abort" → __end__
default → cursor_review
```

---

### approval_gate_router

Routes after human approval gate (when approval_gates enabled).

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
next_decision == "continue" → pre_implementation
next_decision == "retry" → planning
next_decision == "abort" → __end__
default → pre_implementation
```

---

## GSD Pattern Routers

### discuss_router

Routes after discussion phase in GSD pattern.

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
next_decision == "escalate" → human_escalation
discussion_complete == true → discuss_complete
needs_clarification == true → human_escalation
discussion phase errors → discuss_retry
default → discuss_complete
```

---

### research_router

Routes after research phase in GSD pattern.

**File**: `orchestrator/langgraph/routers/general.py`

**Decision Logic**:
```
next_decision == "escalate" → human_escalation
research_complete == true → research_complete
research_errors (non-critical) → research_complete (best-effort)
critical research errors → human_escalation
default → research_complete
```

---

## WorkflowDecision Enum

All routers check the `next_decision` field which uses these values:

| Value | Meaning |
|-------|---------|
| `continue` | Proceed to next phase/task |
| `retry` | Retry current phase/task |
| `escalate` | Escalate to human for help |
| `abort` | Stop the workflow entirely |

---

## Deadlock Detection

The task loop includes deadlock detection in `_check_for_available_tasks_or_escalate()`:

```python
def _check_for_available_tasks_or_escalate(state, default_route):
    # Returns human_escalation if:
    # - No tasks exist
    # - All incomplete tasks are blocked by unmet dependencies
    # - All remaining tasks have failed

    # Returns default_route if:
    # - All tasks completed (loop will end at select_task)
    # - At least one task is available (pending with deps met)
```

This prevents infinite loops when tasks remain but cannot progress.
