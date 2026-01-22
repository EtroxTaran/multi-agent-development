---
description: Create implementation plan with task breakdown
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "TodoWrite", "AskUserQuestion"]
---

# Planning Phase

Create an implementation plan from PRODUCT.md with interactive task breakdown.

## Prerequisites

- `PRODUCT.md` must exist
- Recommended: `CONTEXT.md` from `/discover`

## Workflow

### 1. Read Context

```
Read: PRODUCT.md (required)
Read: CONTEXT.md (if exists)
Read: CLAUDE.md (if exists)
```

### 2. Analyze Requirements

Extract from PRODUCT.md:
- Feature scope
- Acceptance criteria
- Technical constraints
- Testing requirements

### 3. Create Task Breakdown

**Task Size Limits**:
- Max 5 files to create
- Max 8 files to modify
- Max 7 acceptance criteria
- Target complexity < 5

**Task Structure**:
```json
{
  "id": "T1",
  "title": "Short descriptive title",
  "acceptance_criteria": ["..."],
  "files_to_create": ["..."],
  "files_to_modify": ["..."],
  "test_files": ["..."],
  "dependencies": []
}
```

### 4. Present Plan

Show in readable format:

```markdown
## Implementation Plan

### T1: Create user model
- **Complexity**: Low
- **Creates**: src/models/user.ts
- **Tests**: tests/models/user.test.ts
- **Dependencies**: None

### T2: Build auth endpoints
- **Complexity**: Medium
- **Creates**: src/routes/auth.ts
- **Modifies**: src/routes/index.ts
- **Dependencies**: T1

---
Total: 2 tasks
Does this plan look correct?
```

### 5. Get Approval

Wait for user to:
- Approve as-is
- Split large tasks
- Merge small tasks
- Reorder tasks
- Add/remove tasks

### 6. Save Plan

After approval, save to `.workflow/plan.json`.

Update `.workflow/state.json`:
- `phase_status.planning = "completed"`
- `current_phase = 2`

## Transition

When approved:
```
Plan saved to .workflow/plan.json

Next: /task T1 - Start first task
      /status  - View progress
```

## More Details

See full skill documentation: `.claude/skills/plan/SKILL.md`
