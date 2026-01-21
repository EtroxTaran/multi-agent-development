# Claude-Specific Rules

<!-- AGENT-SPECIFIC: Only applies to Claude -->
<!-- Version: 4.0 -->
<!-- Updated: 2026-01-21 - Added file boundaries, external projects, parallel workers -->

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
# Nested project (in projects/ directory)
./scripts/init.sh run <project-name>

# External project (any directory)
./scripts/init.sh run --path /path/to/project

# With parallel workers (experimental)
./scripts/init.sh run <project-name> --parallel 3
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

---

## File Boundary Enforcement (CRITICAL)

The orchestrator has **strict file write boundaries**. This prevents accidental modification of application code.

### Orchestrator CAN Write To:
```
projects/<name>/.workflow/**        <- Workflow state and phase outputs
projects/<name>/.project-config.json <- Project configuration
```

### Orchestrator CANNOT Write To:
```
projects/<name>/src/**              <- Application source (worker only)
projects/<name>/tests/**            <- Tests (worker only)
projects/<name>/lib/**              <- Libraries (worker only)
projects/<name>/app/**              <- App code (worker only)
projects/<name>/CLAUDE.md           <- Worker context (user provides)
projects/<name>/PRODUCT.md          <- Specification (user provides)
projects/<name>/*.py, *.ts, etc.    <- Code files (worker only)
```

### How It Works
The `orchestrator/utils/boundaries.py` module enforces these rules:
- `validate_orchestrator_write(project_dir, path)` - Returns True/False
- `ensure_orchestrator_can_write(project_dir, path)` - Raises `OrchestratorBoundaryError` if invalid

### Using Safe Write Methods
Always use these methods in ProjectManager:
```python
# Write to .workflow/
project_manager.safe_write_workflow_file(project_name, "phases/planning/plan.json", content)

# Write project config
project_manager.safe_write_project_config(project_name, config_dict)
```

### Error Handling
If you attempt to write outside boundaries:
```
OrchestratorBoundaryError: Orchestrator cannot write to 'src/main.py'.
Only .workflow/ and .project-config.json are writable by orchestrator.
```

---

## Nested Architecture

This system uses a two-layer nested architecture:

```
meta-architect/                     <- OUTER LAYER (You - Orchestrator)
|-- CLAUDE.md                       <- Your context (workflow rules)
|-- orchestrator/                   <- Python orchestration module
|   |-- utils/
|   |   |-- boundaries.py           <- File write boundary enforcement
|   |   +-- worktree.py             <- Git worktree for parallel workers
|   +-- project_manager.py          <- Project lifecycle management
|-- scripts/                        <- Agent invocation scripts
+-- projects/                       <- Project containers (nested mode)
    +-- <project-name>/             <- INNER LAYER (Worker Claude)
        |-- Documents/              <- Product vision, architecture docs
        |-- CLAUDE.md               <- Worker context (coding rules)
        |-- GEMINI.md               <- Gemini context
        |-- .cursor/rules           <- Cursor context
        |-- PRODUCT.md              <- Feature specification
        |-- .workflow/              <- Orchestrator-writable state
        |-- src/                    <- Worker-only: Application code
        +-- tests/                  <- Worker-only: Tests
```

---

## Project Modes

### Mode 1: Nested Projects (Default)
Projects live inside `projects/` directory:
```bash
./scripts/init.sh init my-app
./scripts/init.sh run my-app
```

### Mode 2: External Projects
Projects can be anywhere on the filesystem:
```bash
# Run workflow on external project
./scripts/init.sh run --path ~/repos/my-project

# Via Python
python -m orchestrator --project-path ~/repos/my-project --start
```

**Requirements for external projects:**
- Must have `PRODUCT.md` with feature specification
- Should have `.workflow/` directory (created automatically)
- Should have context files (CLAUDE.md, etc.)

### Checking Project Mode
```python
from orchestrator.project_manager import ProjectManager

pm = ProjectManager(root_dir)
project_dir = pm.get_project(path=Path("/external/path"))
is_external = pm.is_external_project(project_dir)  # True
```

---

## Primary Responsibilities

1. **Manage Projects**: Initialize, list, and track projects
2. **Read Specifications**: Read `PRODUCT.md` and `Documents/`
3. **Create Plans**: Write plans to `.workflow/phases/planning/plan.json`
4. **Coordinate Reviews**: Call Cursor/Gemini for plan/code review
5. **Spawn Workers**: Spawn worker Claude for implementation
6. **Resolve Conflicts**: Make final decisions when reviewers disagree

## You Do NOT

- Write application code in `src/`, `lib/`, `app/`
- Write tests in `tests/` or `test/`
- Modify context files (CLAUDE.md, GEMINI.md, PRODUCT.md)
- Make implementation decisions (the plan does that)

---

## Your Phases

| Phase | Your Role | Files You Write |
|-------|-----------|-----------------|
| 1 - Planning | Create plan.json | `.workflow/phases/planning/plan.json` |
| 2 - Validation | Coordinate Cursor + Gemini | `.workflow/phases/validation/` |
| 3 - Implementation | **Spawn worker Claude** | None (worker writes code) |
| 4 - Verification | Coordinate Cursor + Gemini | `.workflow/phases/verification/` |
| 5 - Completion | Generate summary | `.workflow/phases/completion/` |

---

## Spawning Worker Claude

### Standard Mode (Single Worker)
```bash
# Spawn worker Claude for implementation
cd projects/<project-name> && claude -p "Implement the feature per plan.json. Follow TDD." \
    --output-format json \
    --allowedTools "Read,Write,Edit,Bash(npm*),Bash(pytest*),Bash(python*)"
```

### Scoped Worker Prompts
For focused tasks, use minimal context prompts:
```
## Task
{description}

## Acceptance Criteria
- {criteria_1}
- {criteria_2}

## Files to Create
- {file_1}
- {file_2}

## Files to Modify
- {file_1}

## Test Files
- {test_file_1}

## Instructions
1. Read only the files listed above
2. Implement using TDD (write/update tests first)
3. Do NOT read orchestration files (.workflow/, plan.json)
4. Signal completion with: <promise>DONE</promise>
```

The worker Claude:
- Reads `projects/<name>/CLAUDE.md` (app-specific coding rules)
- Has NO access to outer orchestration context
- Writes code and tests
- Reports results back as JSON

---

## Parallel Workers (Experimental)

For independent tasks, spawn multiple workers using git worktrees:

### How It Works
1. Create isolated git worktrees for each worker
2. Workers operate in separate directories without conflicts
3. Changes are merged back via cherry-pick
4. Worktrees are cleaned up after completion

### Command Line Usage
```bash
# Run with 3 parallel workers
./scripts/init.sh run my-app --parallel 3

# Environment variable
export PARALLEL_WORKERS=3
./scripts/init.sh run my-app
```

### Programmatic Usage
```python
from orchestrator.project_manager import ProjectManager

pm = ProjectManager(root_dir)
tasks = [
    {"id": "task-1", "prompt": "Implement feature A", "title": "Feature A"},
    {"id": "task-2", "prompt": "Implement feature B", "title": "Feature B"},
    {"id": "task-3", "prompt": "Implement feature C", "title": "Feature C"},
]

results = pm.spawn_parallel_workers(
    project_name="my-app",
    tasks=tasks,
    max_workers=3,
    timeout=600,
)

for result in results:
    if result["success"]:
        print(f"Task {result['task_id']} completed: {result.get('commit_hash', 'N/A')}")
    else:
        print(f"Task {result['task_id']} failed: {result.get('error')}")
```

### Using WorktreeManager Directly
```python
from orchestrator.utils.worktree import WorktreeManager

# Context manager ensures cleanup
with WorktreeManager(project_dir) as wt_manager:
    # Create worktrees
    wt1 = wt_manager.create_worktree("task-1")
    wt2 = wt_manager.create_worktree("task-2")

    # Workers operate in worktrees...

    # Merge changes back
    wt_manager.merge_worktree(wt1, "Implement task 1")
    wt_manager.merge_worktree(wt2, "Implement task 2")
# Worktrees automatically cleaned up
```

### Requirements
- Project must be a git repository
- Tasks must be independent (no shared file modifications)
- Each task should have clear file boundaries

### Limitations
- Merge conflicts can occur if tasks modify the same files
- Not suitable for tasks with dependencies on each other
- Requires more system resources (disk space for worktrees)

---

## Calling Review Agents

```bash
# Call Cursor for security/code review (runs inside project dir)
bash scripts/call-cursor.sh <prompt-file> <output-file> projects/<name>

# Call Gemini for architecture review (runs inside project dir)
bash scripts/call-gemini.sh <prompt-file> <output-file> projects/<name>
```

---

## Project Management Commands

### Shell Script
```bash
# Initialize new project (nested)
./scripts/init.sh init <project-name>

# List projects
./scripts/init.sh list

# Run workflow (nested project)
./scripts/init.sh run <project-name>

# Run workflow (external project)
./scripts/init.sh run --path /path/to/project

# Run with parallel workers
./scripts/init.sh run <project-name> --parallel 3

# Check status
./scripts/init.sh status <project-name>
```

### Python CLI
```bash
# Project management
python -m orchestrator --init-project <name>
python -m orchestrator --list-projects

# Nested project workflow
python -m orchestrator --project <name> --start
python -m orchestrator --project <name> --resume
python -m orchestrator --project <name> --status

# External project workflow
python -m orchestrator --project-path /path/to/project --start
python -m orchestrator --project-path ~/repos/my-app --status

# Other operations
python -m orchestrator --project <name> --health
python -m orchestrator --project <name> --reset
python -m orchestrator --project <name> --rollback 3
```

---

## Workflow State

Project workflow state is stored in `.workflow/`:
```
.workflow/
|-- state.json                      <- Current workflow state
|-- checkpoints.db                  <- LangGraph checkpoints (SQLite)
+-- phases/
    |-- planning/
    |   +-- plan.json               <- Implementation plan
    |-- validation/
    |   |-- cursor_feedback.json    <- Cursor validation
    |   +-- gemini_feedback.json    <- Gemini validation
    |-- implementation/
    |   +-- task_results/           <- Per-task results
    |-- verification/
    |   |-- cursor_review.json      <- Cursor code review
    |   +-- gemini_review.json      <- Gemini architecture review
    +-- completion/
        +-- summary.json            <- Final summary
```

---

## Context Isolation Rules

1. **Outer context** (this file): Workflow rules, coordination, phase management
2. **Inner context** (`projects/<name>/CLAUDE.md`): Coding standards, TDD, implementation

Never mix these contexts:
- Don't include coding instructions in orchestration prompts
- Don't include workflow instructions in worker prompts
- Let each layer do its job

---

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

1. **File Boundary Enforcement**: Orchestrator can only write to `.workflow/` and `.project-config.json`
2. **Sequential File Writing**: Only the `implementation` node writes code. Cursor and Gemini are read-only reviewers.
3. **Human Escalation**: When max retries exceeded or worker needs clarification, workflow pauses via `interrupt()` for human input.
4. **State Persistence**: SqliteSaver enables checkpoint/resume from any point.
5. **Transient Error Recovery**: Exponential backoff with jitter for recoverable errors.

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
- **Parallel execution**: Independent tasks can run in parallel with git worktrees

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

---

## Error Reference

### OrchestratorBoundaryError
**Cause**: Attempted to write to a path outside allowed boundaries
**Solution**: Use `safe_write_workflow_file()` or `safe_write_project_config()` methods
```
OrchestratorBoundaryError: Orchestrator cannot write to 'src/main.py'.
Only .workflow/ and .project-config.json are writable by orchestrator.
```

### WorktreeError
**Cause**: Git worktree operation failed
**Solution**: Ensure project is a git repository, check for uncommitted changes
```
WorktreeError: '/path/to/project' is not a git repository. Worktrees require git.
```

### Project Not Found
**Cause**: Project doesn't exist in projects/ directory
**Solution**: Initialize project first or use `--project-path` for external projects
```
Error: Project 'my-app' not found
```
