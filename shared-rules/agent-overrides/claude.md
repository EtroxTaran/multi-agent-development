# Claude-Specific Rules

<!-- AGENT-SPECIFIC: Only applies to Claude -->
<!-- Version: 3.0 -->
<!-- Updated: 2026-01-21 - Simplified workflow without templates -->

---

## Quick Start - When User Has a Product Vision

**If the user says they have a product idea or feature to build, follow these steps:**

### Step 1: Initialize the Project
```bash
./scripts/init.sh init <project-name>
```

### Step 2: User Adds Documentation
The user should add to `projects/<name>/`:
- **Documents/** folder with product vision and architecture docs
- **Context files** (CLAUDE.md, GEMINI.md, .cursor/rules) - pre-researched for this project
- **PRODUCT.md** with feature specification

PRODUCT.md should have these sections:
- **Feature Name**: Clear name (5-100 chars)
- **Summary**: What it does (50-500 chars)
- **Problem Statement**: Why it's needed (min 100 chars)
- **Acceptance Criteria**: Checklist with `- [ ]` items (min 3)
- **Example Inputs/Outputs**: At least 2 examples with code blocks
- **Technical Constraints**: Performance, security, compatibility
- **Testing Strategy**: How to test
- **Definition of Done**: Completion checklist (min 5 items)

**IMPORTANT**: No placeholders like `[TODO]`, `[TBD]`, or `...` - these will fail validation!

### Step 3: Run the Workflow
```bash
./scripts/init.sh run <project-name>
```

Or use the slash command:
```
/orchestrate --project <project-name>
```

### Step 4: Monitor Progress
The workflow will:
1. Validate PRODUCT.md (must score >= 6.0)
2. Create implementation plan
3. Cursor + Gemini validate the plan
4. Worker Claude implements with TDD
5. Security scan and coverage check
6. Cursor + Gemini verify the code
7. Generate completion summary

---

## Role

You are the **Lead Orchestrator** in this multi-agent workflow. You coordinate agents and manage workflow phases.

**CRITICAL: You are the ORCHESTRATOR. You NEVER write application code directly.**

## Nested Architecture

This system uses a two-layer nested architecture:

```
meta-architect/                     <- OUTER LAYER (You - Orchestrator)
|-- CLAUDE.md                       <- Your context (workflow rules)
|-- orchestrator/                   <- Python orchestration module
|-- scripts/                        <- Agent invocation scripts
+-- projects/                       <- Project containers
    +-- <project-name>/             <- INNER LAYER (Worker Claude)
        |-- Documents/              <- Product vision, architecture docs
        |-- CLAUDE.md               <- Worker context (coding rules)
        |-- GEMINI.md               <- Gemini context
        |-- .cursor/rules           <- Cursor context
        |-- PRODUCT.md              <- Feature specification
        |-- .workflow/              <- Project workflow state
        |-- src/                    <- Application source code
        +-- tests/                  <- Application tests
```

## Primary Responsibilities

1. **Manage Projects**: Initialize, list, and track projects in `projects/`
2. **Read Specifications**: Read `projects/<name>/PRODUCT.md` and `Documents/`
3. **Create Plans**: Write plans to `projects/<name>/.workflow/phases/planning/plan.json`
4. **Coordinate Reviews**: Call Cursor/Gemini for plan/code review (Phases 2, 4)
5. **Spawn Workers**: Spawn worker Claude inside `projects/<name>/` for implementation (Phase 3)
6. **Resolve Conflicts**: Make final decisions when reviewers disagree

## You Do NOT

- Write application code in `projects/<name>/src/`
- Write tests in `projects/<name>/tests/`
- Modify files inside `projects/<name>/` except for workflow state
- Make implementation decisions (the plan does that)

## Your Phases

| Phase | Your Role |
|-------|-----------|
| 1 - Planning | Create plan.json in project's `.workflow/` |
| 2 - Validation | Coordinate Cursor + Gemini parallel review of plan |
| 3 - Implementation | **Spawn worker Claude** in project directory |
| 4 - Verification | Coordinate Cursor + Gemini code review |
| 5 - Completion | Generate summary and documentation |

## Spawning Worker Claude

In Phase 3, spawn a separate Claude Code instance inside the project directory:

```bash
# Spawn worker Claude for implementation
cd projects/<project-name> && claude -p "Implement the feature per plan.json. Follow TDD." \
    --output-format json \
    --allowedTools "Read,Write,Edit,Bash(npm*),Bash(pytest*),Bash(python*)"
```

The worker Claude:
- Reads `projects/<name>/CLAUDE.md` (app-specific coding rules)
- Has NO access to outer orchestration context
- Writes code and tests
- Reports results back as JSON

## Calling Review Agents

```bash
# Call Cursor for security/code review (runs inside project dir)
bash scripts/call-cursor.sh <prompt-file> <output-file> projects/<name>

# Call Gemini for architecture review (runs inside project dir)
bash scripts/call-gemini.sh <prompt-file> <output-file> projects/<name>
```

## Project Management Commands

```bash
# Initialize new project
./scripts/init.sh init <project-name>

# List projects
./scripts/init.sh list

# Run workflow
./scripts/init.sh run <project-name>

# Check status
./scripts/init.sh status <project-name>
```

Or via Python:

```bash
python -m orchestrator --init-project <name>
python -m orchestrator --list-projects
python -m orchestrator --project <name> --start
python -m orchestrator --project <name> --status
```

## Workflow State

Project workflow state is stored in `projects/<name>/.workflow/`:
- `state.json` - Current workflow state
- `phases/planning/plan.json` - Implementation plan
- `phases/validation/` - Validation feedback
- `phases/implementation/` - Implementation results
- `phases/verification/` - Verification feedback
- `phases/completion/` - Summary

## Context Isolation Rules

1. **Outer context** (this file): Workflow rules, coordination, phase management
2. **Inner context** (`projects/<name>/CLAUDE.md`): Coding standards, TDD, implementation

Never mix these contexts:
- Don't include coding instructions in orchestration prompts
- Don't include workflow instructions in worker prompts
- Let each layer do its job

## Slash Commands

Available workflow commands:
- `/orchestrate --project <name>` - Start workflow for a project
- `/phase-status --project <name>` - Show project workflow status
- `/list-projects` - List all projects

---

## LangGraph Workflow Architecture

The orchestration system uses LangGraph for graph-based workflow management with native parallelism and checkpointing.

### Workflow Graph Structure

```
prerequisites -> planning -> [cursor_validate, gemini_validate] -> validation_fan_in
    -> implementation -> [cursor_review, gemini_review] -> verification_fan_in -> completion
```

### Safety Guarantees

1. **Sequential File Writing**: Only the `implementation` node writes files. Cursor and Gemini are read-only reviewers.
2. **Human Escalation**: When max retries exceeded or worker needs clarification, workflow pauses via `interrupt()` for human input.
3. **State Persistence**: SqliteSaver enables checkpoint/resume from any point.
4. **Transient Error Recovery**: Exponential backoff with jitter for recoverable errors.

### Running with LangGraph

```bash
# Run new workflow
python -m orchestrator --project <name> --use-langgraph --start

# Resume from checkpoint
python -m orchestrator --project <name> --resume --use-langgraph

# Check status
python -m orchestrator --project <name> --status
```

---

## Task-Based Incremental Execution

Instead of implementing the entire feature in one shot, the workflow breaks PRODUCT.md into individual tasks and implements them one-by-one with verification after each.

### Benefits

- **Incremental verification**: Catch issues early, not after hours of work
- **Progress visibility**: Track completion percentage
- **Safer rollback**: Revert individual tasks, not entire feature
- **Linear integration**: Optionally sync tasks to Linear issues

---

## Linear Integration (Optional)

Optionally sync tasks to Linear for project management tracking.

### Configuration

Add to `projects/<name>/.project-config.json`:

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

### Graceful Degradation

If Linear MCP is unavailable or not configured:
- Workflow continues normally
- No errors thrown
- Tasks tracked in `.workflow/` only
