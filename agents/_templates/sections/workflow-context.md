# Workflow Context

## Where You Fit

This is a **5-phase workflow**:

| Phase | Description | Agents |
|-------|-------------|--------|
| 1 | Planning | A01 (Planner), A02 (Architect) |
| 2 | Validation | A07, A08 review plans |
| 3 | Implementation | A03 (Tests), A04 (Code), A05 (Bugs), A06 (Refactor), A09-A12 |
| 4 | Verification | A07, A08 review code |
| 5 | Completion | Summary generation |

**Your phase**: {{PHASE}}

## State Files

The orchestrator tracks state in SurrealDB. You do NOT need to manage state files.

## Task Assignment

You receive tasks via prompts that include:
- `task_id`: Unique identifier (e.g., "T001")
- `title`: What to accomplish
- `acceptance_criteria`: Checklist for completion
- `files_to_create`: New files you should create
- `files_to_modify`: Existing files to change
- `dependencies`: Tasks that must complete first (already done)
