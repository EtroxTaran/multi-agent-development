# Claude-Specific Rules

<!-- AGENT-SPECIFIC: Only applies to Claude -->
<!-- Version: 5.0 -->
<!-- Updated: 2026-01-22 - Added autonomous mode for fully automated execution -->

---

## Quick Start - When User Has a Product Vision

**If the user says they have a product idea or feature to build, follow these steps:**

### Step 1: Initialize the Project
```bash
./scripts/init.sh init <project-name>
```

### Step 2: User Adds Documentation

The user should add to `projects/<name>/`:

**Required:**
- **Docs/** folder with documentation (any structure)
- **Docs/PRODUCT.md** with feature specification

**Flexible Docs/ Structure:**
The Docs/ folder can have ANY structure - flat, nested, however makes sense for your project.
The only requirement is `PRODUCT.md` exists somewhere in Docs/ (usually at root).
All `.md` files in Docs/ and subfolders are read automatically.

```
projects/<name>/
├── Docs/                              <- Documentation (any structure)
│   ├── PRODUCT.md                     <- Feature specification (REQUIRED)
│   └── **/*.md                        <- Any other docs (optional)
├── CLAUDE.md                          <- Worker coding standards (optional)
├── GEMINI.md                          <- Gemini context (optional)
├── .cursor/rules                      <- Cursor context (optional)
└── src/                               <- Application code
```

**PRODUCT.md should have these sections:**
- **Feature Name**: Clear name (5-100 chars)
- **Summary**: What it does (50-500 chars)
- **Problem Statement**: Why it's needed (min 100 chars)
- **Acceptance Criteria**: Checklist with `- [ ]` items (min 3)
- **Example Inputs/Outputs**: At least 2 examples with code blocks
- **Technical Constraints**: Performance, security, compatibility
- **Testing Strategy**: How to test
- **Definition of Done**: Completion checklist (min 5 items)

**IMPORTANT**: No placeholders like `[TODO]`, `[TBD]`, or `...` - these will fail validation!

**Flexible Documentation**: The orchestrator adapts to whatever documentation exists. More docs = better context for planning. At minimum, `Docs/PRODUCT.md` is required.

### Step 3: Run the Workflow
```bash
# Nested project (in projects/ directory)
./scripts/init.sh run <project-name>

# External project (any directory)
./scripts/init.sh run --path /path/to/project

# With parallel workers (experimental)
./scripts/init.sh run <project-name> --parallel 3

# Fully autonomous mode (no human consultation)
./scripts/init.sh run <project-name> --autonomous
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

## Storage Architecture (SurrealDB Required)

All workflow state is stored in **SurrealDB**. There is no local file fallback - if there's no internet, AI agents can't work anyway.

### Prerequisites
```bash
# Set SurrealDB connection URL (required)
export SURREAL_URL=wss://your-surreal-instance.example.com/rpc

# Or for local development
export SURREAL_URL=ws://localhost:8000/rpc
```

### Database Per Project
Each project gets its own isolated database namespace:
- Database name: `project_{project_name}`
- Tables: `workflow_state`, `phase_outputs`, `logs`, `sessions`, `budgets`, `checkpoints`, `audit_trail`

### What Gets Stored Where

| Data Type | Table | Description |
|-----------|-------|-------------|
| Workflow state | `workflow_state` | Current phase, status, errors |
| Plans | `phase_outputs` | Phase 1 planning output |
| Validation feedback | `phase_outputs` | Cursor/Gemini feedback (phase 2) |
| Task results | `phase_outputs` | Implementation results (phase 3) |
| Code reviews | `phase_outputs` | Cursor/Gemini reviews (phase 4) |
| Completion summary | `phase_outputs` | Final summary (phase 5) |
| UAT documents | `logs` | User acceptance test docs |
| Escalations | `logs` | Escalation records |
| Approvals | `logs` | Human approval audit trail |

### Fail-Fast Validation
The orchestrator validates DB connection on startup:
```python
from orchestrator.db.config import require_db

require_db()  # Raises DatabaseRequiredError if SURREAL_URL not set
```

### Error Handling
If SurrealDB is not configured:
```
DatabaseRequiredError: SurrealDB is required but SURREAL_URL environment variable is not set.
```

---

## Code Boundary Enforcement (CRITICAL)

The orchestrator **never writes application code**. This is enforced by architecture, not just convention.

### Orchestrator Role
- Reads specifications and documentation
- Creates plans (stored in DB)
- Coordinates review agents
- Spawns worker Claude for implementation
- Stores workflow state in SurrealDB

### Orchestrator CANNOT
- Write to `src/`, `lib/`, `app/`, `tests/`
- Modify `*.py`, `*.ts`, `*.js`, `*.go`, etc.
- Change context files (CLAUDE.md, GEMINI.md)
- Edit PRODUCT.md specification

### Worker Claude Role
- Reads plan from orchestrator
- Writes application code
- Writes tests
- Reports results back to orchestrator

---

## Nested Architecture

This system uses a two-layer nested architecture:

```
conductor/                     <- OUTER LAYER (You - Orchestrator)
|-- CLAUDE.md                       <- Your context (workflow rules)
|-- orchestrator/                   <- Python orchestration module
|   |-- db/                         <- SurrealDB integration
|   |   |-- repositories/           <- Data access layer
|   |   +-- schema.py               <- Database schema
|   |-- utils/
|   |   +-- worktree.py             <- Git worktree for parallel workers
|   +-- project_manager.py          <- Project lifecycle management
|-- scripts/                        <- Agent invocation scripts
+-- projects/                       <- Project containers (nested mode)
    +-- <project-name>/             <- INNER LAYER (Worker Claude)
        |-- Docs/                   <- Documentation (any structure)
        |   |-- PRODUCT.md          <- Feature specification (REQUIRED)
        |   +-- **/*.md             <- Any other docs (flexible)
        |-- CLAUDE.md               <- Worker context (coding rules)
        |-- GEMINI.md               <- Gemini context
        |-- .cursor/rules           <- Cursor context
        |-- src/                    <- Worker-only: Application code
        +-- tests/                  <- Worker-only: Tests

State Storage: SurrealDB (database per project: project_{name})
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
- Must have `Docs/PRODUCT.md` with feature specification (or `PRODUCT.md` in root as fallback)
- Should have `Docs/` folder with supporting documentation
- Should have context files (CLAUDE.md, etc.)
- SurrealDB connection required (`SURREAL_URL` environment variable)

### Checking Project Mode
```python
from orchestrator.project_manager import ProjectManager

pm = ProjectManager(root_dir)
project_dir = pm.get_project(path=Path("/external/path"))
is_external = pm.is_external_project(project_dir)  # True
```

---

## Execution Modes

The workflow supports two execution modes:

### Interactive Mode (Default)
The default mode pauses for human input at critical decision points:
- When errors need resolution (escalation)
- At configured approval gates
- When clarification is needed

```bash
# Interactive mode (default)
./scripts/init.sh run my-app

# Via Python
python -m orchestrator --project my-app --start
```

### Autonomous Mode
Run fully autonomously without human consultation. The orchestrator makes all decisions based on best practices:

```bash
# Autonomous mode
./scripts/init.sh run my-app --autonomous

# Via Python
python -m orchestrator --project my-app --start --autonomous
```

**Autonomous Mode Behavior:**
- **Escalations**: Automatically retries up to 3 times, then aborts or skips
- **Approval Gates**: Auto-approved with audit trail
- **Clarifications**: Proceeds with best-guess implementation
- **Validation Failures**: Retries, then skips to next phase
- **Verification Failures**: Retries, then completes with warnings

**When to Use Autonomous Mode:**
- Well-defined projects with comprehensive Docs/ folder
- Projects with clear Docs/PRODUCT.md and supporting documentation
- Projects where you trust the AI to make reasonable decisions
- Overnight or batch processing runs
- When you want to see results quickly and fix issues later

**When NOT to Use Autonomous Mode:**
- New or experimental projects
- Projects without Docs/ folder (will abort)
- Projects with ambiguous requirements
- When you need to verify each step
- Critical production code changes

---

## Primary Responsibilities

1. **Manage Projects**: Initialize, list, and track projects
2. **Discover Documentation**: Recursively read all docs from `Docs/` folder
3. **Read Specifications**: Read `Docs/PRODUCT.md` and supporting documentation
4. **Create Plans**: Store plans in SurrealDB `phase_outputs` table
5. **Coordinate Reviews**: Call Cursor/Gemini for plan/code review
6. **Spawn Workers**: Spawn worker Claude for implementation
7. **Resolve Conflicts**: Make final decisions when reviewers disagree

## You Do NOT

- Write application code in `src/`, `lib/`, `app/`
- Write tests in `tests/` or `test/`
- Modify context files (CLAUDE.md, GEMINI.md, PRODUCT.md)
- Make implementation decisions (the plan does that)

---

## Your Phases

| Phase | Your Role | DB Storage |
|-------|-----------|------------|
| 0 - Product Validation | Validate PRODUCT.md | `phase_outputs` (type=product_validation) |
| 0.5 - Discovery | Read all docs from Docs/ | `workflow_state.docs_index` |
| 1 - Planning | Create implementation plan | `phase_outputs` (type=plan, task_breakdown) |
| 2 - Validation | Coordinate Cursor + Gemini | `phase_outputs` (type=*_feedback) |
| 3 - Implementation | **Spawn worker Claude** | `phase_outputs` (type=task_result) |
| 4 - Verification | Coordinate Cursor + Gemini | `phase_outputs` (type=*_review) |
| 5 - Completion | Generate summary | `phase_outputs` (type=summary) |

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

## Workflow State (SurrealDB)

All workflow state is stored in SurrealDB, organized by phase:

### Phase Outputs Table (`phase_outputs`)
| Phase | Output Type | Description |
|-------|-------------|-------------|
| 0 | `product_validation` | PRODUCT.md validation results |
| 1 | `plan` | Implementation plan |
| 1 | `task_breakdown` | Tasks and milestones |
| 2 | `cursor_feedback` | Cursor validation feedback |
| 2 | `gemini_feedback` | Gemini validation feedback |
| 2 | `validation_consolidated` | Merged validation results |
| 3 | `pre_implementation_check` | Environment readiness |
| 3 | `task_result` | Per-task implementation results |
| 3 | `implementation_result` | Overall implementation output |
| 4 | `security_scan` | Security scan results |
| 4 | `coverage_check` | Test coverage results |
| 4 | `build_verification` | Build/type check results |
| 4 | `task_verification` | Per-task verification |
| 4 | `cursor_review` | Cursor code review |
| 4 | `gemini_review` | Gemini architecture review |
| 4 | `verification_consolidated` | Merged review results |
| 5 | `summary` | Final completion summary |

### Logs Table (`logs`)
| Log Type | Description |
|----------|-------------|
| `research` | Research agent findings |
| `research_aggregated` | Combined research results |
| `discussion` | Developer preference capture |
| `approval_context` | Approval gate context |
| `approval_response` | Human approval decisions |
| `escalation` | Escalation records |
| `blocker` | Blocking issues |
| `clarification_answers` | Human clarification responses |
| `uat_document` | User acceptance test docs |

### Querying State
```python
from orchestrator.db.repositories import get_phase_output_repository, get_logs_repository

# Get plan for a project
repo = get_phase_output_repository("my-project")
plan = await repo.get_by_type(phase=1, output_type="plan")

# Get all logs
logs_repo = get_logs_repository("my-project")
escalations = await logs_repo.get_by_type("escalation")
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

1. **Code Boundary Enforcement**: Orchestrator never writes application code - only spawns workers.
2. **DB-Only State**: All workflow state stored in SurrealDB, not local files.
3. **Sequential Implementation**: Only the `implementation` node writes code. Cursor and Gemini are read-only reviewers.
4. **Human Escalation**: When max retries exceeded or worker needs clarification, workflow pauses via `interrupt()` for human input.
5. **State Persistence**: SurrealDB enables checkpoint/resume from any point.
6. **Transient Error Recovery**: Exponential backoff with jitter for recoverable errors.

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

## Task Granularity

Tasks are enforced to be small and focused using multi-dimensional complexity assessment. Research shows file counts alone are insufficient - a task modifying 3 tightly coupled files may be harder than one modifying 10 isolated files.

### Complexity Scoring (0-13 Scale)

Task complexity is assessed using five components:

| Component | Points | Description |
|-----------|--------|-------------|
| `file_scope` | 0-5 | Files touched (0.5 pts each, capped) |
| `cross_file_deps` | 0-2 | Coupling between directories/layers |
| `semantic_complexity` | 0-3 | Algorithm/integration difficulty |
| `requirement_uncertainty` | 0-2 | Vague or unclear requirements |
| `token_penalty` | 0-1 | Context budget exceeded |

**Complexity Levels**:
- **LOW (0-4)**: Safe for autonomous execution
- **MEDIUM (5-7)**: Requires monitoring
- **HIGH (8-10)**: Consider decomposition
- **CRITICAL (11-13)**: Must decompose

### Soft Limits (Guidance Only)

File limits generate warnings but complexity score drives splits:

| Guidance | Default | Purpose |
|----------|---------|---------|
| `max_files_to_create` | 5 | Context guidance |
| `max_files_to_modify` | 8 | Change scope guidance |
| `max_acceptance_criteria` | 7 | Scope clarity |
| `complexity_threshold` | 5.0 | Auto-split trigger |

### Auto-Split Strategies

Split strategy is selected based on dominant complexity factor:

1. **Files Strategy** - When file_scope is dominant
   - Groups files by directory
   - Keeps related files together

2. **Layers Strategy** - When cross_file_deps is dominant
   - Separates by architectural layer
   - Reduces coupling between tasks

3. **Criteria Strategy** - When semantic complexity is dominant
   - Splits by acceptance criteria
   - Creates focused, clear sub-tasks

**Example**:
```
Task T1 (complexity: 8.5 - HIGH):
  Dominant factor: cross_file_deps
  Strategy: LAYERS

After Auto-Split:
  T1-a: data layer files, deps=[]
  T1-b: business layer files, deps=[T1-a]
  T1-c: presentation layer files, deps=[T1-b]
```

### Configuration

Override defaults in `.project-config.json`:

```json
{
  "task_size_limits": {
    "max_files_to_create": 5,
    "max_files_to_modify": 8,
    "max_criteria_per_task": 7,
    "complexity_threshold": 5.0,
    "auto_split": true
  }
}
```

### Best Practices for Planning

- Target complexity score **< 5** per task
- Prefer **many small tasks** over few large tasks
- Keep related files in the same architectural layer together
- Watch for high semantic complexity keywords: algorithm, async, concurrent, distributed

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
- Tasks tracked in SurrealDB only

---

## Error Reference

### DatabaseRequiredError
**Cause**: SurrealDB connection not configured
**Solution**: Set `SURREAL_URL` environment variable
```
DatabaseRequiredError: SurrealDB is required but SURREAL_URL environment variable is not set.
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

### Connection Pool Exhausted
**Cause**: Too many concurrent database connections
**Solution**: Reduce parallelism or increase pool size
```
ConnectionPoolExhausted: No available connections in pool
```

---

## User Preferences

**Shell**: Fish shell
- Use `source .venv/bin/activate.fish` (not `.venv/bin/activate`)
- Use Fish-compatible syntax (e.g., `set -x VAR value` instead of `export VAR=value`)

**Python Environment**:
- Virtual env: `.venv/`
- Run tests: `.venv/bin/python -m pytest tests/ -v`
- Run scripts: `.venv/bin/python script.py`
