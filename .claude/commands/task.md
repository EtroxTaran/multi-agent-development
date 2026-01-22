---
description: Implement a specific task by ID
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash", "Task", "TodoWrite"]
---

# Task Implementation

Implement a single task from the plan using TDD.

## Usage

```
/task T1
/task T1-a
```

## Prerequisites

- Plan exists at `.workflow/plan.json`
- Task ID exists in the plan
- Dependencies are completed

## Workflow

### 1. Load Task

Read `.workflow/plan.json` and find the task by ID.

### 2. Check Dependencies

Verify all dependencies are completed:
```
Dependencies: T1, T2
  T1: completed ✓
  T2: completed ✓
Ready to proceed.
```

If incomplete:
```
Cannot start T3 - dependencies not met:
  T2: pending ← Not done
Run /task T2 first.
```

### 3. Show Task Scope

```markdown
## Task T1: Create user model

### Acceptance Criteria
- [ ] User model with id, email, password_hash
- [ ] Email must be unique

### Files to Create
- src/models/user.ts

### Test Files
- tests/models/user.test.ts

Ready to implement?
```

### 4. Confirm Start

Wait for user confirmation.

### 5. Implement with TDD

Use Task tool to spawn worker:

```
Task(
  subagent_type="general-purpose",
  prompt="""
  ## Task: {title}

  ## Acceptance Criteria
  {criteria}

  ## Instructions
  1. Write failing tests FIRST
  2. Implement code to pass tests
  3. Run tests to verify
  4. Signal: TASK_COMPLETE
  """
)
```

### 6. Report Status

```markdown
## Task T1 Complete

### Files Created
- src/models/user.ts (45 lines)

### Tests
- 4 tests passing

### Acceptance Criteria
- [x] User model with id, email, password_hash
- [x] Email must be unique

---
Next: /task T2 or /status
```

### 7. Update State

Update task status in `.workflow/plan.json`:
- `status: "completed"`
- `completed_at: timestamp`

## Key Behaviors

**DO**:
- Show scope before starting
- Wait for confirmation
- Use TDD (tests first)
- Report clear status
- Update state after

**DON'T**:
- Start without confirmation
- Skip tests
- Modify files outside scope
- Leave task incomplete

## More Details

See full skill documentation: `.claude/skills/task/SKILL.md`
