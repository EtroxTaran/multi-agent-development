---
description: Show current workflow status and progress
allowed-tools: ["Read", "Glob"]
---

# Workflow Status

Show current progress at a glance.

## Usage

```
/status
```

## Shows

- Current phase
- Task progress (completed/total)
- Any blockers
- Next recommended action

## State Files

Check:
- `.workflow/state.json` - Workflow state
- `.workflow/plan.json` - Task breakdown

## Output Format

### No Workflow Started

```
## Project Status

No workflow started yet.

Quick start:
  /discover - Read docs, create PRODUCT.md
  /plan     - Create task breakdown
```

### Active Workflow

```
## Project Status

### Current Phase: Implementation

### Progress

[====================----------] 50%

Completed: 3/6 tasks

| Task | Title | Status |
|------|-------|--------|
| T1 | User model | done |
| T2 | Password service | done |
| T3 | JWT service | done |
| T4 | Login endpoint | pending |
| T5 | Register endpoint | pending |
| T6 | Auth middleware | pending |

### Next

Continue with: /task T4
```

### With Blockers

```
## Project Status

### Current Phase: Implementation (BLOCKED)

### Blocker
Task T3 failed: Cannot find module '@prisma/client'

Suggested fix: npm install @prisma/client

### Next
Fix blocker, then: /task T3
```

## Phase Mapping

| Phase | Name | Next Skill |
|-------|------|------------|
| 0 | Discovery | `/discover` |
| 1 | Planning | `/plan` |
| 2 | Validation | `/validate` |
| 3 | Implementation | `/task <id>` |
| 4 | Verification | `/verify` |
| 5 | Completion | (done) |

## Related Skills

- `/discover` - Start discovery
- `/plan` - Create tasks
- `/task <id>` - Implement task
- `/orchestrate` - Full automation

## More Details

See full skill documentation: `.claude/skills/status/SKILL.md`
