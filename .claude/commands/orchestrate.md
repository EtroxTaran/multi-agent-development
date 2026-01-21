---
description: Start or resume the 5-phase multi-agent workflow
allowed-tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Task", "TodoWrite"]
---

# Multi-Agent Workflow Orchestration

Start or resume the 5-phase workflow to implement features using the nested orchestration architecture.

## Quick Start

```bash
# Initialize a new project
./scripts/init.sh init my-feature

# User adds:
# - Documents/ with product vision and architecture docs
# - CLAUDE.md, GEMINI.md, .cursor/rules (context files)
# - PRODUCT.md (feature specification)

# Start workflow for the project
./scripts/init.sh run my-feature

# Or via Python
python -m orchestrator --project my-feature --use-langgraph --start

# Resume an interrupted workflow
python -m orchestrator --project my-feature --resume --use-langgraph
```

## Nested Architecture

This system uses a two-layer architecture:

- **Outer Layer** (meta-architect/): Orchestration - you coordinate agents here
- **Inner Layer** (projects/<name>/): Application code - worker Claude writes code here

**CRITICAL**: As the orchestrator, you NEVER write application code directly. You spawn a worker Claude inside the project directory for Phase 3.

## Project Management

```bash
# Initialize new project
./scripts/init.sh init my-app

# List all projects
./scripts/init.sh list

# Run workflow
./scripts/init.sh run my-app

# Check status
./scripts/init.sh status my-app

# Or via Python
python -m orchestrator --list-projects
python -m orchestrator --project my-app --status
```

## Workflow Phases

| Phase | Name | Your Role |
|-------|------|-----------|
| 1 | Planning | Create plan.json in project's `.workflow/` |
| 2 | Validation | Coordinate Cursor + Gemini parallel review |
| 3 | Implementation | **Spawn worker Claude** in project directory |
| 4 | Verification | Coordinate Cursor + Gemini code review |
| 5 | Completion | Generate summary and documentation |

## Context Loading

For a project, read these files in order:
1. `projects/<name>/Documents/` - Product vision and architecture
2. `projects/<name>/PRODUCT.md` - Feature specification
3. `projects/<name>/.workflow/state.json` - Current workflow state

## Instructions

### Starting a New Workflow

1. Ensure project exists: `./scripts/init.sh list`
2. Read `projects/<name>/Documents/` and `PRODUCT.md` thoroughly
3. Create `plan.json` with:
   - Feature overview
   - File changes required
   - Implementation steps
   - Test strategy
4. Save to `projects/<name>/.workflow/phases/planning/plan.json`
5. Update `projects/<name>/.workflow/state.json` to phase 2
6. Proceed to validation

### Validation (Phase 2)

Run both agents in parallel, pointing at the project directory:

```bash
bash scripts/call-cursor.sh \
    projects/<name>/.workflow/phases/validation/cursor-prompt.md \
    projects/<name>/.workflow/phases/validation/cursor-feedback.json \
    projects/<name>

bash scripts/call-gemini.sh \
    projects/<name>/.workflow/phases/validation/gemini-prompt.md \
    projects/<name>/.workflow/phases/validation/gemini-feedback.json \
    projects/<name>
```

### Implementation (Phase 3)

**DO NOT write code yourself.** Spawn a worker Claude:

```bash
cd projects/<name> && claude -p "Implement the feature per plan.json. Follow TDD. \
Write tests first, then implementation code. Report results as JSON." \
    --output-format json \
    --allowedTools "Read,Write,Edit,Bash(npm*),Bash(pytest*),Bash(python*)"
```

The worker Claude:
- Reads `projects/<name>/CLAUDE.md` (coding rules)
- Writes code in `src/` and tests in `tests/`
- Reports results back to you

### Verification (Phase 4)

Run both agents to verify implementation:

```bash
bash scripts/call-cursor.sh \
    projects/<name>/.workflow/phases/verification/cursor-prompt.md \
    projects/<name>/.workflow/phases/verification/cursor-review.json \
    projects/<name>

bash scripts/call-gemini.sh \
    projects/<name>/.workflow/phases/verification/gemini-prompt.md \
    projects/<name>/.workflow/phases/verification/gemini-review.json \
    projects/<name>
```

Both must approve with score >= 7.0.

### Completion (Phase 5)

Generate summary documentation in `projects/<name>/.workflow/phases/completion/`.

## Approval Thresholds

- **Phase 2 (Validation)**: Score >= 6.0, no blocking issues
- **Phase 4 (Verification)**: Score >= 7.0, BOTH agents must approve

## Output

Update `projects/<name>/.workflow/state.json` after each phase transition.
Save all artifacts to the appropriate phase directory.
