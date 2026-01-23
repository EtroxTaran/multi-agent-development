# Claude Code Context


<!-- AUTO-GENERATED from shared-rules/ -->
<!-- Last synced: 2026-01-23 17:03:56 -->
<!-- DO NOT EDIT - Run: python scripts/sync-rules.py -->

Instructions for Claude Code as lead orchestrator.


# Claude-Specific Rules

<!-- AGENT-SPECIFIC: Only applies to Claude -->
<!-- Version: 5.1 -->
<!-- Updated: 2026-01-23 - Added web research config and HITL documentation -->

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

## Research Configuration

The research phase can search the web for up-to-date documentation, security advisories, and best practices.

### Default Behavior (No Config Needed)
- **WebSearch** and **WebFetch** tools are enabled
- Web research agent runs automatically alongside codebase analysis agents
- Searches for: documentation links, CVEs, best practices, common pitfalls

### Enable Perplexity Deep Research (Optional)
For more comprehensive research with citations, enable Perplexity MCP tools:

```json
{
  "research": {
    "perplexity_enabled": true
  }
}
```

**Perplexity Tools Added:**
- `mcp__perplexity__perplexity_search` - Web search
- `mcp__perplexity__perplexity_ask` - Conversational research
- `mcp__perplexity__perplexity_research` - Deep research with citations

### Disable Web Research (Rare)
```json
{
  "research": {
    "web_research_enabled": false
  }
}
```

### Full Research Config
```json
{
  "research": {
    "web_research_enabled": true,
    "web_research_timeout": 60,
    "perplexity_enabled": false,
    "fallback_on_web_failure": true
  }
}
```

---

## Interactive HITL Mode

When running in interactive mode (default), the workflow will pause and prompt for user input at critical points.

### When HITL Prompts Appear
- **Escalations**: When errors occur and need human decision
- **Approval Gates**: When configured phases require approval
- **Clarifications**: When the system needs additional information

### HITL Actions for Escalations
| Action | Description |
|--------|-------------|
| `retry` | Retry the current phase |
| `skip` | Skip to next phase |
| `continue` | Continue (you fixed it externally) |
| `answer_clarification` | Answer clarification questions |
| `abort` | Abort the workflow |

### HITL Actions for Approvals
| Action | Description |
|--------|-------------|
| `approve` | Approve and continue |
| `reject` | Reject and abort workflow |
| `request_changes` | Request changes and retry phase |

### Non-Interactive Defaults
In CI or non-TTY environments, safe defaults are used:
- **Escalations**: Abort
- **Approvals**: Reject

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


## Available Skills

The following skills are available for use via the specified commands:

| Skill | Command | Description |
|-------|---------|-------------|
| ADD-LESSON | /add-lesson | No description provided |
| API-CONTRACTS-AND-VALIDATION | /api-contracts-and-validation | Define and validate API contracts using Zod |
| CALL-CURSOR | /call-cursor | No description provided |
| CALL-GEMINI | /call-gemini | No description provided |
| CODEBASE-VISUALIZER | /codebase-visualizer | Extract diagrams and explain complex logic |
| DISCOVER | /discover | No description provided |
| E2E-WEBAPP-TESTING | /e2e-webapp-testing | Create resilient E2E tests using Playwright/Cypress |
| FRONTEND-DEV-GUIDELINES | n/a | Standards for React / TypeScript development |
| GIT-COMMIT-CONVENTIONAL | /git-commit-conventional | Generate conventional commit messages with strict formatting rules |
| GIT-COMMITTER-ATOMIC | /git-committer-atomic | Plan and create atomic commits ordered by dependencies |
| GIT-WORKFLOW-HELPER | /git-workflow-helper | Handle common git scenarios, conflicts, and hook failures |
| GITHUB-ACTIONS-DEBUGGING | /github-actions-debugging | Debug and fix GitHub Actions CI/CD failures |
| IMPLEMENT-TASK | /implement-task | No description provided |
| LIST-PROJECTS | /list-projects | No description provided |
| ORCHESTRATE | /orchestrate | No description provided |
| PHASE-STATUS | /phase-status | No description provided |
| PLAN | /plan | No description provided |
| PLAN-FEATURE | /plan-feature | No description provided |
| REFACTOR-SAFE-WORKFLOW | /refactor-safe-workflow | Orchestrate safe refactoring with multi-step validation |
| RELEASE-NOTES-AND-CHANGELOG | /release-notes-and-changelog | Generate release notes from git history |
| RESOLVE-CONFLICT | /resolve-conflict | No description provided |
| SKILL-CREATOR | /skill-creator | Scaffold new skills with standard directory structure |
| SKILL-EVAL | /skill-eval | Evaluate skill performance against test cases |
| SKILLS | /skills | No description provided |
| STATUS | /status | No description provided |
| SYNC-RULES | /sync-rules | No description provided |
| TASK | /task | No description provided |
| TDD-OVERNIGHT-DEV | /tdd-overnight-dev | Autonomous Feature-to-Commit TDD loop for long-running sessions |
| TEST-WRITER-UNIT-INTEGRATION | /test-writer-unit-integration | Generate standardized unit and integration tests |
| TS-STRICT-GUARDIAN | /ts-strict-guardian | Enforce strict TypeScript guidelines and safety |
| UI-DESIGN-SYSTEM | /ui-design-system | Authoritative UI/UX Design System Guide based on EtroxTaran/Uiplatformguide |
| VALIDATE-PLAN | /validate-plan | No description provided |
| VERIFY-CODE | /verify-code | No description provided |
| WORKFLOW-MANAGER | /workflow-manager | No description provided |


---


# Shared Rules


The following rules apply to all agents in the workflow.


---

# Core Rules (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 1.0 -->
<!-- Last Updated: 2026-01-20 -->

## Workflow Rules

### Phase Execution
- Never skip phases - each phase builds on the previous
- Always check `.workflow/state.json` before starting work
- Update state.json after completing each phase
- Maximum 3 iterations per phase before escalation

### TDD Requirement
- Write failing tests FIRST
- Implement code to make tests pass
- Refactor while keeping tests green
- Never mark implementation complete with failing tests

### Approval Thresholds
- Phase 2 (Validation): Score >= 6.0, no blocking issues
- Phase 4 (Verification): Score >= 7.0, BOTH agents must approve

## Communication Rules

### Output Format
- Always output valid JSON when requested
- Include `agent` field identifying yourself
- Include `status` field: approved | needs_changes | error
- Include `score` field: 1-10 scale

### Context Files
- Always read CLAUDE.md for workflow rules (or agent-specific context file)
- Always read PRODUCT.md for requirements
- Check .workflow/state.json for current state

### Documentation Access
- **Use the Context Map**: Start at `docs/readme.md` to find the correct file.
- **No Monoliths**: Do not assume `CONDUCTOR-GUIDE.md` or similar huge files exist. Follow the links.


## Error Handling

### When Errors Occur
- Log the error clearly with context
- Suggest remediation steps
- Don't proceed with broken state
- Escalate to human if blocked (via workflow interrupt)

### When Uncertain
- Ask for clarification rather than guess
- Document assumptions made
- Flag uncertainty in output

## Quality Standards

### Code Changes
- Keep changes minimal and focused
- Don't add features beyond what's requested
- Don't refactor unrelated code
- Preserve existing patterns unless explicitly changing them

### Security
- Check for OWASP Top 10 vulnerabilities
- Never commit secrets or credentials
- Validate all external input
- Use parameterized queries for databases

## Collaboration Rules

### Handoffs Between Agents
- Write clear prompts with full context
- Include relevant file paths
- Specify expected output format
- Document any assumptions

### Conflict Resolution
- Security issues: Cursor's assessment preferred (0.8 weight)
- Architecture issues: Gemini's assessment preferred (0.7 weight)
- When equal: escalate to human decision

---

# Coding Standards (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 1.0 -->
<!-- Last Updated: 2026-01-20 -->

## General Principles

### Simplicity
- Prefer simple solutions over clever ones
- Don't over-engineer - solve the current problem
- Three similar lines of code is better than a premature abstraction
- Only add complexity when clearly necessary

### Consistency
- Follow existing patterns in the codebase
- Match the style of surrounding code
- Use consistent naming conventions
- Don't mix paradigms unnecessarily

## Documentation & Naming

### Naming Conventions
- **Strict Lowercase**: All file and directory names must be lowercase (e.g., `documentation/` not `Documentation/`, `product-vision.md` not `ProductVision.md`).
- **Separators**: Use hyphens (kebab-case) or underscores (snake_case) for multi-word names.
- **Exceptions**: Specific system files if required by tools (e.g., `Dockerfile`, `Makefile`), but standard docs must be lowercase.

### Documentation Structure
- **Split by Topic**: Avoid monolithic files like `product.md`. Split into `product-vision.md`, `technical-decisions.md`, etc.
- **Task Linkage**: Technical tasks must clearly link to User Stories.
- **Detail Level**: Tasks must specify frameworks, interfaces, and methods used.
- **Best Practices**: Explicitly research and cite best practices before implementation.

## Code Organization

### Files
- One module/class per file (generally)
- Group related functionality together
- Keep files under 500 lines when possible
- Use clear, descriptive file names

### Functions
- Single responsibility per function
- Keep functions under 50 lines when possible
- Clear input/output types
- Meaningful parameter names

### Comments
- Only add comments where logic isn't self-evident
- Don't add obvious comments ("increment counter")
- Document WHY, not WHAT
- Keep comments up to date with code changes

## Error Handling

### Patterns
- Handle errors at appropriate boundaries
- Don't swallow errors silently
- Provide actionable error messages
- Log with sufficient context for debugging

### Validation
- Validate at system boundaries (user input, external APIs)
- Trust internal code and framework guarantees
- Don't add redundant validation

## Testing

### Test Structure
- Arrange-Act-Assert pattern
- One assertion per test when possible
- Clear test names describing behavior
- Test edge cases and error conditions

### Coverage
- Focus on behavior, not line coverage
- Test public interfaces, not implementation details
- Integration tests for critical paths
- Don't test framework/library code

## Language-Specific

### Python
- Follow PEP 8 style guide
- Use type hints for public interfaces
- Prefer f-strings over .format()
- Use pathlib for file paths

### TypeScript (Standard)
- **Strict Mode**: Always use `strict: true`. No implicit any.
- **Types**: Explicitly define return types for all public functions.
- **No Any**: Never use `any`. Use `unknown` and narrow types if needed.
- **Interfaces vs Types**: Use `interface` for object definitions/APIs, `type` for unions/intersections.
- **Async**: Always await promises or explicitly ignore.

### React (Standard)
- **Components**: Functional components only. Use PascalCase.
- **Hooks**: Custom hooks must start with `use`. Follow strict hook rules.
- **State**: Keep state local. Lift only when necessary.
- **Re-renders**: Use `memo`, `useMemo`, `useCallback` only when performance issues specially identified (avoid premature optimization).
- **Styling**: Use module-scoped CSS or Utility-first (Tailwind) if project configured.

### Shell Scripts
- Use `set -e` for error handling
- Quote variables: `"$VAR"` not `$VAR`
- Check command existence before using
- Use shellcheck for validation

---

# Guardrails (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 2.0 -->
<!-- Last Updated: 2026-01-21 -->

## Security Guardrails

### Never Do
- Commit secrets, API keys, or credentials
- Use eval() or exec() with user input
- Build SQL queries with string concatenation
- Disable security features without explicit approval
- Store passwords in plaintext
- Trust user input without validation

### Always Do
- Use parameterized queries for databases
- Escape output to prevent XSS
- Validate and sanitize all external input
- Use secure defaults (HTTPS, secure cookies)
- Follow least privilege principle

---

## Orchestrator Storage Guardrails

**These rules apply specifically to the orchestrator (Claude as lead orchestrator).**

### Storage Architecture
All workflow state is stored in **SurrealDB** - there is no local file storage for workflow state.

### Orchestrator CAN
- Store workflow state in SurrealDB (via storage adapters)
- Read project files (Docs/, PRODUCT.md, CLAUDE.md)
- Spawn worker Claude for code changes

### Orchestrator CANNOT Write To
```
projects/<name>/src/**               <- Application source code
projects/<name>/tests/**             <- Test files
projects/<name>/test/**              <- Test files (alternative)
projects/<name>/lib/**               <- Library code
projects/<name>/app/**               <- Application code
projects/<name>/*.py                 <- Python files at root
projects/<name>/*.ts, *.js, *.tsx    <- TypeScript/JavaScript files
projects/<name>/*.go, *.rs           <- Go/Rust files
projects/<name>/CLAUDE.md            <- Worker context file
projects/<name>/GEMINI.md            <- Gemini context file
projects/<name>/PRODUCT.md           <- Feature specification
projects/<name>/.cursor/**           <- Cursor context files
```

### Never Do (Orchestrator)
- Write application code directly (spawn workers instead)
- Write workflow state to local files (use DB)
- Change project context files (CLAUDE.md, GEMINI.md)
- Run workflow without SurrealDB connection

### Always Do (Orchestrator)
- Use storage adapters for workflow state
- Use repositories for phase outputs and logs
- Spawn worker Claude for any code changes
- Verify DB connection before starting workflow

### Error Recovery
If you see `DatabaseRequiredError`:
1. Set `SURREAL_URL` environment variable
2. Verify SurrealDB instance is running
3. Check network connectivity to database

---

## Code Quality Guardrails

### Never Do
- Leave debug code (console.log, print, debugger)
- Commit commented-out code
- Create empty catch blocks
- Use magic numbers without constants
- Ignore linter/type errors
- Use `any` type (unless strictly necessary for migration, comment required)
- Suppress linter rules without valid reason and comment

### Always Do
- Run tests before marking complete
- Check for regressions in existing tests
- Follow existing code patterns
- Clean up temporary files
- Fix all linter errors before committing
- Ensure `npm run typecheck` leads to 0 errors

---

## Workflow Guardrails

### Never Do
- Skip phases in the workflow
- Proceed without required approvals
- Ignore blocking issues
- Mark tasks complete when they're not

### Always Do
- Update workflow state in DB after phase transitions
- Store phase outputs in `phase_outputs` table
- Log decisions and escalations in `logs` table
- Check prerequisites before starting phases

---

## File Operation Guardrails

### Never Do
- Delete files without confirmation
- Overwrite without reading first
- Create files in wrong locations
- Leave orphaned test files

### Always Do
- Read files before editing
- Verify paths before operations
- Use project-relative paths
- Clean up created temporary files

---

## Git Guardrails

### Never Do
- Force push to main/master
- Commit directly to protected branches
- Use --no-verify without approval
- Commit merge conflict markers

### Always Do
- Create descriptive commit messages
- Check git status before committing
- Stage only intended changes
- Pull before pushing

---

## Git Worktree Guardrails

**For parallel worker execution using git worktrees.**

### Never Do
- Create worktrees for dependent tasks
- Modify the same file in multiple worktrees
- Leave orphaned worktrees after completion
- Merge worktrees with conflicts without resolution

### Always Do
- Use WorktreeManager context manager for auto-cleanup
- Verify tasks are independent before parallel execution
- Check worktree status before merging
- Handle cherry-pick failures gracefully

---

## API/CLI Guardrails

### Never Do
- Use deprecated API endpoints
- Ignore rate limits
- Make destructive calls without confirmation
- Expose internal errors to users

### Always Do
- Handle API errors gracefully
- Respect retry/backoff patterns
- Validate API responses
- Log API calls for debugging

---

## External Project Guardrails

**For projects outside the nested `projects/` directory.**

### Before Running on External Project
- Verify `PRODUCT.md` exists with proper structure
- Check project is a git repository (for worktree support)
- Confirm no uncommitted changes (recommended)
- Verify SurrealDB connection is configured

### Never Do
- Assume external projects have same structure as nested
- Run workflow without validating PRODUCT.md first
- Modify files outside expected locations

### Always Do
- Use `--project-path` flag for external projects
- Validate project structure before starting workflow
- Ensure `SURREAL_URL` environment variable is set

---

# CLI Reference (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 2.0 -->
<!-- Last Updated: 2026-01-21 -->

## Correct CLI Usage

This is the authoritative reference for CLI tool invocation. Always use these patterns.

---

## Claude Code CLI

**Command**: `claude`

### Non-Interactive Mode
```bash
claude -p "Your prompt here" --output-format json
```

### Key Flags (Basic)
| Flag | Purpose | Example |
|------|---------|---------|
| `-p` | Prompt (non-interactive) | `-p "What is 2+2?"` |
| `--output-format` | Output format | `--output-format json` |
| `--allowedTools` | Restrict tools | `--allowedTools "Read,Write,Edit"` |
| `--max-turns` | Limit turns | `--max-turns 10` |

### Enhanced Flags (Use These!)
| Flag | Purpose | When to Use |
|------|---------|-------------|
| `--permission-mode plan` | Plan before implementing | Tasks touching ≥3 files OR high complexity |
| `--resume <session-id>` | Continue previous session | Ralph loop iterations (preserves debugging context) |
| `--session-id <id>` | Set session ID for tracking | New task sessions |
| `--json-schema <path>` | Enforce output structure | Use `schemas/plan-schema.json` or `schemas/tasks-schema.json` |
| `--max-budget-usd <n>` | Limit API cost | Always set (default: $1.00 per invocation) |
| `--fallback-model <model>` | Failover model | Use `sonnet` (default) or `haiku` |

### Decision Matrix: When to Use Enhanced Features

| Scenario | Plan Mode | Session | Budget | Schema |
|----------|-----------|---------|--------|--------|
| Simple 1-2 file task | ❌ | ❌ | ✅ $0.50 | ❌ |
| Multi-file task (≥3 files) | ✅ | ❌ | ✅ $1.00 | ✅ if structured output |
| High complexity task | ✅ | ❌ | ✅ $2.00 | ✅ |
| Ralph loop iteration 1 | ❌ | New session | ✅ $0.50 | ❌ |
| Ralph loop iteration 2+ | ❌ | ✅ Resume | ✅ $0.50 | ❌ |
| Planning phase | ✅ Always | ❌ | ✅ $1.00 | ✅ plan-schema.json |

### Full Example (Enhanced)
```bash
# Complex multi-file task with all features
claude -p "Implement user authentication" \
    --output-format json \
    --permission-mode plan \
    --max-budget-usd 2.00 \
    --fallback-model sonnet \
    --json-schema schemas/tasks-schema.json \
    --allowedTools "Read,Write,Edit,Bash(npm*),Bash(pytest*)" \
    --max-turns 50

# Ralph loop iteration with session continuity
claude -p "Fix failing tests" \
    --output-format json \
    --resume T1-abc123def456 \
    --max-budget-usd 0.50 \
    --allowedTools "Read,Write,Edit,Bash(pytest*)" \
    --max-turns 15
```

### Basic Example
```bash
claude -p "Analyze this code" \
    --output-format json \
    --allowedTools "Read,Grep,Glob" \
    --max-turns 5
```

---

## Cursor Agent CLI

**Command**: `cursor-agent`

### Non-Interactive Mode
```bash
cursor-agent --print --output-format json "Your prompt here"
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--print` or `-p` | Non-interactive mode | `--print` |
| `--output-format` | Output format | `--output-format json` |
| `--force` | Skip confirmations | `--force` |

### Prompt Position
**IMPORTANT**: Prompt is a POSITIONAL argument at the END, not a flag value.

### Full Example
```bash
cursor-agent --print \
    --output-format json \
    --force \
    "Review this code for security issues"
```

### Common Mistakes
- `cursor-agent -p "prompt"` - Wrong! `-p` means `--print`, not prompt
- Prompt must be LAST argument

---

## Gemini CLI

**Command**: `gemini`

### Non-Interactive Mode
```bash
gemini --yolo "Your prompt here"
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--yolo` | Auto-approve tool calls | `--yolo` |
| `--model` | Select model | `--model gemini-2.0-flash` |

### Important Notes
- Gemini does NOT support `--output-format`
- Output must be wrapped in JSON externally if needed
- Prompt is a positional argument

### Full Example
```bash
gemini --model gemini-2.0-flash \
    --yolo \
    "Review architecture of this system"
```

### Common Mistakes
- `gemini --output-format json` - Wrong! Flag doesn't exist
- `gemini -p "prompt"` - Wrong! No `-p` flag

---

## Python Orchestrator

**Command**: `python -m orchestrator`

### Project Management
```bash
# Initialize new project
python -m orchestrator --init-project <name>

# List all projects
python -m orchestrator --list-projects
```

### Workflow Commands (Nested Projects)
```bash
# Start workflow for a nested project
python -m orchestrator --project <name> --start
python -m orchestrator --project <name> --use-langgraph --start

# Resume interrupted workflow
python -m orchestrator --project <name> --resume

# Check status
python -m orchestrator --project <name> --status

# Health check
python -m orchestrator --project <name> --health

# Reset workflow
python -m orchestrator --project <name> --reset

# Rollback to phase
python -m orchestrator --project <name> --rollback 3
```

### Workflow Commands (External Projects)
```bash
# Start workflow for external project
python -m orchestrator --project-path /path/to/project --start
python -m orchestrator --project-path ~/repos/my-app --use-langgraph --start

# Check status
python -m orchestrator --project-path /path/to/project --status
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--project`, `-p` | Project name (nested) | `--project my-app` |
| `--project-path` | External project path | `--project-path ~/repos/my-app` |
| `--start` | Start workflow | `--start` |
| `--resume` | Resume from checkpoint | `--resume` |
| `--status` | Show workflow status | `--status` |
| `--autonomous` | Run fully autonomously (no human input) | `--autonomous` |
| `--use-langgraph` | Use LangGraph mode | `--use-langgraph` |
| `--health` | Health check | `--health` |
| `--reset` | Reset workflow | `--reset` |
| `--rollback` | Rollback to phase (1-5) | `--rollback 3` |
| `--list-projects` | List all projects | `--list-projects` |
| `--init-project` | Initialize project | `--init-project my-app` |

---

## Shell Script Wrappers

### init.sh - Main Entry Point

```bash
# Check prerequisites
./scripts/init.sh check

# Initialize new project
./scripts/init.sh init <project-name>

# List all projects
./scripts/init.sh list

# Run workflow (nested project)
./scripts/init.sh run <project-name>

# Run workflow (external project)
./scripts/init.sh run --path /path/to/project

# Run with parallel workers (experimental)
./scripts/init.sh run <project-name> --parallel 3

# Run fully autonomously (no human consultation)
./scripts/init.sh run <project-name> --autonomous

# Combine flags
./scripts/init.sh run <project-name> --autonomous --parallel 3

# Check status
./scripts/init.sh status <project-name>

# Show help
./scripts/init.sh help
```

### init.sh Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--path` | External project path | `run --path ~/repos/app` |
| `--parallel` | Parallel workers count | `run my-app --parallel 3` |
| `--autonomous` | Run without human consultation | `run my-app --autonomous` |

### call-cursor.sh
```bash
bash scripts/call-cursor.sh <prompt-file> <output-file> [project-dir]
```

### call-gemini.sh
```bash
bash scripts/call-gemini.sh <prompt-file> <output-file> [project-dir]
```

---

## Environment Variables

### Orchestrator
```bash
# Enable LangGraph mode
export ORCHESTRATOR_USE_LANGGRAPH=true

# Enable Ralph Wiggum loop for TDD
export USE_RALPH_LOOP=auto  # auto | true | false

# Set parallel workers
export PARALLEL_WORKERS=3
```

### Agent CLI Overrides
```bash
export CURSOR_MODEL=gpt-4-turbo      # Override Cursor model
export GEMINI_MODEL=gemini-2.0-flash  # Override Gemini model
```

---

## Python Orchestrator Modules (For Claude as Tech Lead)

These modules are available for autonomous decision-making. **Use them directly** without asking for permission.

### Session Manager
```python
from orchestrator.agents import SessionManager

# Automatic session continuity for Ralph loop iterations
manager = SessionManager(project_dir)

# Get resume args for existing session (maintains debugging context)
args = manager.get_resume_args("T1")  # Returns ["--resume", "session-id"] or []

# Create new session when starting a task
session = manager.create_session("T1")

# Close session when task completes
manager.close_session("T1")
```

**Decision Rule**: Always use session continuity for Ralph loop iterations 2+. Fresh sessions for new tasks.

### Error Context Manager
```python
from orchestrator.agents import ErrorContextManager

# Automatically record and learn from failures
manager = ErrorContextManager(project_dir)

# Record error when task fails
context = manager.record_error(
    task_id="T1",
    error_message="AssertionError: expected 5, got 3",
    attempt=1,
    stderr=stderr_output,
)

# Build enhanced retry prompt (includes error history + suggestions)
retry_prompt = manager.build_retry_prompt("T1", original_prompt)

# Clear errors when task succeeds
manager.clear_task_errors("T1")
```

**Decision Rule**: Always record errors. Always use enhanced retry prompts. Clear on success.

### Budget Manager
```python
from orchestrator.agents import BudgetManager

manager = BudgetManager(project_dir)

# Check before spending
if manager.can_spend("T1", 0.50):
    # Proceed with invocation
    pass

# Record actual spend
manager.record_spend("T1", "claude", actual_cost)

# Get budget for --max-budget-usd flag
budget = manager.get_invocation_budget("T1")  # Returns float

# Check remaining
remaining = manager.get_task_remaining("T1")
```

**Decision Rule**: Always pass `--max-budget-usd` to CLI. Default $1.00 per invocation, $0.50 for Ralph iterations.

### Audit Trail
```python
from orchestrator.audit import get_project_audit_trail

trail = get_project_audit_trail(project_dir)

# Record invocations (auto-integrated into BaseAgent.run())
with trail.record("claude", "T1", prompt) as entry:
    result = run_command(...)
    entry.set_result(success=True, exit_code=0, cost_usd=0.05)

# Query for debugging
history = trail.get_task_history("T1")
stats = trail.get_statistics()
```

**Decision Rule**: Audit trail is automatic. Use `query()` and `get_statistics()` for debugging failed tasks.

### ClaudeAgent (Enhanced)
```python
from orchestrator.agents import ClaudeAgent

agent = ClaudeAgent(
    project_dir,
    enable_session_continuity=True,  # Default: True
    default_fallback_model="sonnet",  # Default: sonnet
    default_budget_usd=1.00,          # Optional: per-invocation limit
)

# Auto-detects when to use plan mode
result = agent.run_task(task)  # Uses plan mode if task.files >= 3

# Or explicit control
result = agent.run(
    prompt,
    task_id="T1",
    use_plan_mode=True,
    budget_usd=2.00,
    output_schema="plan-schema.json",
)
```

**Decision Rule**: Let `should_use_plan_mode()` decide automatically. Override only when you have specific reasons.

---

## Autonomous Decision Guidelines

**DO automatically (no permission needed):**
- Use plan mode for ≥3 files or high complexity
- Resume sessions for Ralph iterations 2+
- Record errors and use enhanced retry prompts
- Set budget limits on all invocations
- Use fallback model (sonnet by default)

**DO NOT do without asking:**
- Skip budget limits entirely
- Force plan mode on simple tasks
- Clear error history before task actually succeeds
- Change project-wide budget limits

**When uncertain, prefer:**
- Plan mode over no plan mode (safer for quality)
- Session continuity over fresh context (better debugging)
- Lower budget with fallback over higher budget (cost control)
- Recording errors over ignoring them (learn from failures)

---

## Quick Reference Table

| Tool | Non-Interactive | Prompt | Output Format |
|------|-----------------|--------|---------------|
| `claude` | `-p "prompt"` | Part of `-p` | `--output-format json` |
| `cursor-agent` | `--print` | Positional (end) | `--output-format json` |
| `gemini` | `--yolo` | Positional | N/A (wrap externally) |

---

## Complete Workflow Examples

### Example 1: New Nested Project
```bash
# 1. Initialize
./scripts/init.sh init my-api

# 2. Add files (manually)
# - projects/my-api/Documents/
# - projects/my-api/PRODUCT.md
# - projects/my-api/CLAUDE.md

# 3. Run workflow
./scripts/init.sh run my-api
```

### Example 2: External Project
```bash
# 1. Ensure project has PRODUCT.md
# 2. Run workflow
./scripts/init.sh run --path ~/repos/existing-project

# Or via Python
python -m orchestrator --project-path ~/repos/existing-project --use-langgraph --start
```

### Example 3: Parallel Implementation
```bash
# Run with 3 parallel workers for independent tasks
./scripts/init.sh run my-app --parallel 3
```

### Example 4: Check and Resume
```bash
# Check status
./scripts/init.sh status my-app

# If paused, resume
python -m orchestrator --project my-app --resume
```

---

# Lessons Learned

<!-- SHARED: This file applies to ALL agents -->
<!-- Add new lessons at the TOP of this file -->
<!-- Version: 1.9 -->
<!-- Last Updated: 2026-01-23 -->

## How to Add a Lesson

When you discover a bug, mistake, or pattern that should be remembered:

1. Add a new entry at the TOP of the "Recent Lessons" section
2. Follow the template format
3. Run `python scripts/sync-rules.py` to propagate

---

## Recent Lessons

### 2026-01-23 - Global Bugfixer and Optimizer Agents

- **Issue**: Bugfixer only caught ~30% of errors (8 nodes had no error routing), Optimizer only evaluated ~10% of agent executions (`last_agent_execution` was never set)
- **Root Cause**: Error handling and evaluation were implemented ad-hoc per node instead of as universal infrastructure; no rich error context for diagnosis
- **Fix**: Implemented comprehensive global agent infrastructure:
  1. **ErrorContext TypedDict**: Rich error info with stack trace, stderr, state snapshot, suggested recovery actions, recoverability classification
  2. **AgentExecution TypedDict**: Tracks all agent calls with prompt, output, duration, cost, model, template name
  3. **Universal Node Wrapper**: `@wrapped_node` decorator catches ALL exceptions, creates ErrorContext, routes to error_dispatch, tracks agent executions
  4. **Execution Tracker**: `ExecutionTracker` class with context manager for consistent agent call tracking
  5. **Auto-Recoverability**: Errors auto-classified as recoverable (TimeoutError, ConnectionError, AssertionError) vs requiring human approval
  6. **Template-Specific Evaluation**: All 9 templates have weighted criteria (planning, validation, code_review, architecture_review, task_implementation, test_writing, bug_fix, fixer_diagnose, fixer_apply)
  7. **State Reducers**: `_append_executions` and `_append_errors` for merging parallel results
  8. **Updated All Agent Nodes**: planning, validation (cursor+gemini), verification (cursor+gemini), task/modes now track executions
- **Prevention**:
  - Use `@wrapped_node` decorator for ALL new nodes
  - Use `create_agent_execution()` helper when calling agents
  - Use `create_error_context()` helper when catching exceptions
  - All errors route through `error_dispatch` node
  - All agent executions flow through `evaluate_agent` node
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/langgraph/state.py` - Added ErrorContext, AgentExecution TypedDicts, helpers, reducers
  - `orchestrator/langgraph/wrappers/__init__.py` - New package exports
  - `orchestrator/langgraph/wrappers/node_wrapper.py` - Universal decorator, AGENT_NODES registry
  - `orchestrator/langgraph/wrappers/execution_tracker.py` - ExecutionTracker class
  - `orchestrator/langgraph/nodes/error_dispatch.py` - Uses rich ErrorContext, SKIP_FIXER_ERROR_TYPES
  - `orchestrator/langgraph/nodes/planning.py` - Tracks agent execution
  - `orchestrator/langgraph/nodes/validation.py` - Tracks cursor/gemini executions
  - `orchestrator/langgraph/nodes/verification.py` - Tracks review executions
  - `orchestrator/langgraph/nodes/task/modes.py` - Tracks implementation execution
  - `orchestrator/langgraph/nodes/evaluate_agent.py` - Template-specific TEMPLATE_CRITERIA for all 9 templates
  - `tests/test_node_wrapper.py` - 16 tests for wrapper
  - `tests/test_global_error_routing.py` - 18 tests for error dispatch
  - `tests/test_global_evaluation.py` - 36 tests for evaluation

### 2026-01-23 - Web Search for Research Agents and HITL User Input

- **Issue**: Research agents relied solely on codebase analysis and training data; workflow interrupts had no interactive CLI for human input
- **Root Cause**: No web search capability for up-to-date documentation/security advisories; non-interactive mode meant users couldn't respond to escalations
- **Fix**: Implemented two enhancements:
  1. **Web Research Agent**: New research agent that searches web for documentation, CVEs, best practices
     - `ResearchConfig` dataclass with configurable tools (WebSearch, WebFetch, Perplexity MCP)
     - Basic web tools ON by default (free, built into Claude Code)
     - Perplexity deep research optional (requires API)
     - Tool selection based on agent `requires_web` field
  2. **Interactive HITL CLI**: Rich-based display and input for workflow interrupts
     - `UserInputManager` routes escalation/approval interrupts
     - `InterruptDisplay` shows context with panels/tables
     - `prompt_helpers` module for reusable menu/confirm/text prompts
     - Auto-detection of interactive mode (TTY check, CI env vars)
     - Safe defaults for non-interactive (abort/reject)
- **Prevention**:
  - Use `ResearchConfig` for web tool configuration
  - Check `requires_web` field before spawning research agents
  - Use `UserInputManager.handle_interrupt()` for HITL processing
  - Test for `is_interactive()` before prompting users
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/config/thresholds.py` - Added ResearchConfig dataclass
  - `orchestrator/langgraph/nodes/research_phase.py` - Web research agent, tool selection
  - `orchestrator/agents/prompts/claude_web_research.md` - Web research prompt template
  - `orchestrator/ui/prompt_helpers.py` - Reusable prompt utilities (new)
  - `orchestrator/ui/interrupt_display.py` - Rich display components (new)
  - `orchestrator/ui/input_manager.py` - UserInputManager class (new)
  - `orchestrator/ui/__init__.py` - Exported new classes
  - `orchestrator/orchestrator.py` - HITL integration in resume_langgraph()

### 2026-01-23 - Dynamic Role Dispatch for Task-Aware Agent Selection

- **Issue**: Conflict resolution between Cursor and Gemini used static weights (0.6/0.4), ignoring task context
- **Root Cause**: All tasks treated equally regardless of whether they're security-focused (Cursor's strength) or architecture-focused (Gemini's strength)
- **Fix**: Implemented Dynamic Role Dispatch system:
  1. **Task Type Inference**: `infer_task_type()` analyzes task title, files, and acceptance criteria
  2. **Role Assignment**: `get_role_assignment()` returns optimal weights based on task type:
     - SECURITY → Cursor 0.8 / Gemini 0.2 (auth, crypto, vulnerability tasks)
     - ARCHITECTURE → Cursor 0.3 / Gemini 0.7 (design patterns, refactoring)
     - OPTIMIZATION → Cursor 0.5 / Gemini 0.5 (performance, caching)
     - GENERAL → Cursor 0.6 / Gemini 0.4 (default)
  3. **Dynamic Weights in Resolver**: `resolve()` accepts optional `cursor_weight`/`gemini_weight` params
  4. **Integration**: Both validation and verification fan-in nodes use task-aware weights
- **Prevention**:
  - Use `infer_task_type()` before conflict resolution
  - Pass role weights to `resolver.resolve()` for task-aware decisions
  - Domain expert's opinion now carries more weight for their specialty
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/config/models.py` - Added TaskType, RoleAssignment, inference functions
  - `orchestrator/review/resolver.py` - Added optional weight params to resolve()
  - `orchestrator/langgraph/nodes/validation.py` - Role dispatch in validation_fan_in_node
  - `orchestrator/langgraph/nodes/verification.py` - Role dispatch in verification_fan_in_node

### 2026-01-23 - Full SurrealDB Migration - Remove File-Based Storage

- **Issue**: Workflow state stored in `.workflow/` files caused issues with state management, made debugging harder, and created unnecessary file boundary complexity
- **Root Cause**: Original design used local files as fallback, but "if there's no internet, AI agents can't work anyway" - the fallback was unnecessary
- **Fix**: Complete migration to SurrealDB as the ONLY storage backend:
  1. **Schema Update**: Added `phase_outputs` and `logs` tables (schema v2.1.0)
  2. **New Repositories**: `PhaseOutputRepository` and `LogsRepository` for type-safe data access
  3. **Storage Adapters**: Removed file fallback from all 5 adapters (workflow, session, budget, checkpoint, audit)
  4. **LangGraph Nodes**: Updated 17 nodes to use DB repositories instead of file writes
  5. **Fail-Fast Validation**: `require_db()` in orchestrator startup
  6. **Migration Script**: `scripts/migrate_workflow_to_db.py` for existing projects
- **Prevention**:
  - Never add file-based fallback for workflow state
  - Use storage adapters and repositories for all state access
  - Validate DB connection at startup before any workflow operations
  - Keep state in SurrealDB tables, not local JSON files
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/db/schema.py` - Added phase_outputs, logs tables
  - `orchestrator/db/repositories/phase_outputs.py` - New repository
  - `orchestrator/db/repositories/logs.py` - New repository
  - `orchestrator/db/config.py` - Added require_db(), DatabaseRequiredError
  - `orchestrator/storage/*.py` - Removed file fallback (5 files)
  - `orchestrator/langgraph/nodes/*.py` - DB storage (17 files)
  - `orchestrator/orchestrator.py` - require_db() at startup
  - `shared-rules/agent-overrides/claude.md` - Documentation updates
  - `shared-rules/guardrails.md` - Storage guardrails
  - `scripts/migrate_workflow_to_db.py` - Migration script

### 2026-01-22 - Native Claude Code Skills Architecture for Token Efficiency

- **Issue**: Python-based orchestration spawning Claude via subprocess was token-inefficient (~13k overhead per spawn) and added complexity
- **Root Cause**: Subprocess spawning duplicates full context to each worker; Python orchestrator added external process management overhead
- **Fix**: Implemented optimized hybrid architecture using native Claude Code features:
  1. **Skills System**: Created 10+ skills in `.claude/skills/` to encode workflow logic:
     - `/orchestrate` - Main workflow orchestration
     - `/plan-feature` - Planning phase with Task tool
     - `/validate-plan` - Parallel Cursor + Gemini validation
     - `/implement-task` - TDD implementation via Task tool
     - `/verify-code` - Parallel code review
     - `/call-cursor`, `/call-gemini` - Agent wrappers
     - `/resolve-conflict` - Conflict resolution
     - `/phase-status`, `/list-projects` - Status utilities
  2. **Task Tool for Workers**: Replace subprocess with native Task tool for 70% token savings
  3. **Bash for External Agents**: Cursor and Gemini called via Bash tool (same CLI, integrated)
  4. **State via Read/Write**: State persistence using native file tools
  5. **Multi-Agent Review Preserved**: Same Cursor + Gemini review at every phase
- **Prevention**:
  - Always prefer Task tool over subprocess for Claude worker spawning
  - Use Skills for reusable workflow patterns
  - Use Bash tool for external CLI agents (Cursor, Gemini)
  - Keep state in JSON files managed by native Read/Write tools
- **Applies To**: claude
- **Files Changed**:
  - `.claude/skills/orchestrate/SKILL.md` (new)
  - `.claude/skills/plan-feature/SKILL.md` (new)
  - `.claude/skills/validate-plan/SKILL.md` (new)
  - `.claude/skills/implement-task/SKILL.md` (new)
  - `.claude/skills/verify-code/SKILL.md` (new)
  - `.claude/skills/call-cursor/SKILL.md` (new)
  - `.claude/skills/call-gemini/SKILL.md` (new)
  - `.claude/skills/resolve-conflict/SKILL.md` (new)
  - `.claude/skills/phase-status/SKILL.md` (new)
  - `.claude/skills/list-projects/SKILL.md` (new)
  - `.claude/skills/sync-rules/SKILL.md` (new)
  - `.claude/skills/add-lesson/SKILL.md` (new)
  - `.claude/commands/orchestrate.md` (updated)
  - `.claude/commands/validate.md` (updated)
  - `.claude/commands/verify.md` (updated)

### 2026-01-22 - Universal Agent Loop Pattern for All Agents

- **Issue**: Ralph Wiggum loop only worked for Claude; Cursor/Gemini couldn't use iterative TDD
- **Root Cause**: Hardcoded Claude CLI, completion patterns, and no model selection
- **Fix**: Implemented Universal Agent Loop with:
  - Agent Adapter Layer: Unified interface for Claude, Cursor, Gemini (`orchestrator/agents/adapter.py`)
  - Model selection: codex-5.2/composer for Cursor, gemini-2.0-flash/pro for Gemini, sonnet/opus/haiku for Claude
  - Verification Strategies: Pluggable tests/lint/security/composite verification
  - Unified Loop Runner: Works with any agent, budget control, error context
  - Completion patterns: `<promise>DONE</promise>` (Claude), `{"status": "done"}` (Cursor), `DONE`/`COMPLETE` (Gemini)
- **Prevention**:
  - Use adapter pattern for new agents
  - Each agent defines its own completion patterns
  - Model selection via env vars: LOOP_AGENT, LOOP_MODEL
  - Enable with USE_UNIFIED_LOOP=true
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/agents/adapter.py` (new - 800 lines)
  - `orchestrator/langgraph/integrations/unified_loop.py` (new - 710 lines)
  - `orchestrator/langgraph/integrations/verification.py` (new - 750 lines)
  - `orchestrator/agents/cursor_agent.py` (modified - model selection)
  - `orchestrator/agents/gemini_agent.py` (modified - model selection)
  - `tests/test_agent_adapters.py` (new - 36 tests)
  - `tests/test_verification_strategies.py` (new - 41 tests)
  - `tests/test_unified_loop.py` (new - 46 tests)

### 2026-01-22 - GSD and Ralph Wiggum Pattern Enhancements

- **Issue**: Workflow lacked structured discussion phase before planning, no research agents, limited execution modes (no HITL), no token tracking, no checkpoint/rollback support, and no UAT document generation
- **Root Cause**: Original implementation focused on basic workflow execution without incorporating proven patterns from GSD (Get Shit Done) and Ralph Wiggum methodologies
- **Fix**: Implemented 12 key improvements across 4 phases:
  1. **Discussion Phase**: Mandatory discussion before planning to capture developer preferences into CONTEXT.md
  2. **Research Agents**: 2 parallel agents (tech_stack, existing_patterns) that analyze codebase before planning
  3. **HITL vs AFK Modes**: ExecutionMode enum for Human-in-the-Loop (pause after each iteration) vs Away-from-Keyboard (autonomous)
  4. **External Hook Scripts**: HookManager for pre/post iteration hooks, stop-check scripts for custom termination logic
  5. **Token/Cost Tracking**: TokenMetrics and TokenUsageTracker for per-iteration cost monitoring with 75% context warning
  6. **UAT Document Generation**: UATGenerator creates verification documents after each completed task
  7. **Checkpoint Support**: CheckpointManager for manual state snapshots with rollback capability
  8. **Handoff Brief Generation**: generate_handoff_node creates session resume documents before workflow ends
  9. **CONTEXT.md Template**: Template for capturing library preferences, architecture decisions, testing philosophy
  10. **Enhanced Ralph Loop**: HookConfig integration, token tracking, HITL pause support
  11. **Workflow Integration**: Updated workflow graph to include discuss → research → product_validation path
  12. **UAT in Verification**: verify_task.py generates UAT documents on task completion
- **Prevention**:
  - Always run discussion phase before planning for new projects
  - Use HITL mode for exploratory or risky implementations
  - Set cost limits to prevent runaway execution costs
  - Create checkpoints before major changes
  - Generate UAT documents for audit trail
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/langgraph/nodes/discuss_phase.py` (new)
  - `orchestrator/langgraph/nodes/research_phase.py` (new)
  - `orchestrator/langgraph/nodes/generate_handoff.py` (new)
  - `orchestrator/langgraph/integrations/hooks.py` (new)
  - `orchestrator/langgraph/integrations/ralph_loop.py` (enhanced with ExecutionMode, TokenMetrics, HookConfig)
  - `orchestrator/langgraph/state.py` (added discussion, research, execution_mode, token_usage fields)
  - `orchestrator/langgraph/workflow.py` (added discuss, research, generate_handoff nodes)
  - `orchestrator/langgraph/routers/general.py` (added discuss_router, research_router)
  - `orchestrator/langgraph/nodes/implement_task.py` (reads CONTEXT.md and research findings)
  - `orchestrator/langgraph/nodes/verify_task.py` (generates UAT documents)
  - `orchestrator/utils/uat_generator.py` (new)
  - `orchestrator/utils/checkpoint.py` (new)
  - `templates/CONTEXT.md.template` (new)
  - `templates/UAT.md.template` (new)
  - `tests/test_uat_generator.py` (new)
  - `tests/test_checkpoint.py` (new)
  - `tests/test_discuss_research_phases.py` (new)
  - `tests/test_ralph_enhancements.py` (new)

### 2026-01-22 - Enhanced CLI Utilization for Quality and Automation

- **Issue**: Claude CLI tools used in basic single-shot manner, missing powerful quality-enhancing features like plan mode, session continuity, schema validation, and audit trails
- **Root Cause**: Enhanced CLI flags (`--permission-mode plan`, `--resume`, `--json-schema`, `--max-budget-usd`) were not utilized by the orchestrator
- **Fix**: Implemented 8 enhancements across 4 phases:
  1. **Plan Mode**: Auto-detect when to use `--permission-mode plan` (files ≥ 3 OR high complexity)
  2. **Session Continuity**: `SessionManager` for `--resume`/`--session-id` across Ralph loop iterations
  3. **Error Context Preservation**: `ErrorContextManager` with auto-classification and suggestions for intelligent retries
  4. **Comprehensive Audit Trail**: Thread-safe JSONL logging of all CLI invocations with timing, costs, and outcomes
  5. **JSON Schema Validation**: `--json-schema` support for structured output enforcement
  6. **Budget Control**: `BudgetManager` with project/task/invocation limits via `--max-budget-usd`
  7. **Fallback Model**: `--fallback-model sonnet` for automatic failover
  8. **Enhanced ClaudeAgent**: Unified interface integrating all features with autonomous decision-making
- **Prevention**:
  - Use plan mode for ≥3 files OR high complexity tasks (automatic)
  - Resume sessions for Ralph iterations 2+ (preserves debugging context)
  - Always record errors and use enhanced retry prompts
  - Set budget limits on all invocations (default $1.00)
  - Use `should_use_plan_mode()` to let agent decide automatically
- **Applies To**: claude
- **Files Changed**:
  - `orchestrator/agents/session_manager.py` (new - 280 lines)
  - `orchestrator/agents/error_context.py` (new - 400 lines)
  - `orchestrator/agents/budget.py` (new - 450 lines)
  - `orchestrator/audit/__init__.py` (new)
  - `orchestrator/audit/trail.py` (new - 350 lines)
  - `orchestrator/agents/claude_agent.py` (major rewrite - 565 lines)
  - `orchestrator/agents/base.py` (modified - audit integration)
  - `orchestrator/agents/__init__.py` (modified - exports)
  - `shared-rules/cli-reference.md` (updated - enhanced flags, decision matrix, autonomous guidelines)
  - `tests/test_session_manager.py` (new - 21 tests)
  - `tests/test_audit_trail.py` (new - 22 tests)
  - `tests/test_error_context.py` (new - 32 tests)
  - `tests/test_budget.py` (new - 25 tests)
  - `tests/test_claude_agent_enhanced.py` (new - 30 tests)

### 2026-01-21 - Enhanced Nested Architecture with Safety Features

- **Issue**: Orchestrator could accidentally write to project code files; no support for external projects or parallel workers
- **Root Cause**: Missing file boundary enforcement; tight coupling between orchestrator and projects; sequential-only worker execution
- **Fix**: Implemented four major enhancements:
  1. **File Boundary Enforcement**: Orchestrator can only write to `.workflow/` and `.project-config.json`. Violations raise `OrchestratorBoundaryError`.
  2. **External Project Mode**: `--project-path` flag allows running workflow on any directory, not just `projects/`.
  3. **Scoped Worker Prompts**: Minimal context prompts focus workers on specific files, preventing context bloat.
  4. **Git Worktree Parallel Workers**: Independent tasks can run in parallel using isolated git worktrees with automatic cleanup.
- **Prevention**:
  - Always use `safe_write_workflow_file()` and `safe_write_project_config()` in orchestrator
  - Use `validate_orchestrator_write()` before any file write
  - Spawn workers for any code changes; orchestrator never writes code
  - Use worktrees only for independent tasks; verify no shared file modifications
- **Applies To**: claude
- **Files Changed**:
  - `orchestrator/utils/boundaries.py` (new)
  - `orchestrator/utils/worktree.py` (new)
  - `orchestrator/project_manager.py` (modified)
  - `orchestrator/orchestrator.py` (modified)
  - `orchestrator/langgraph/nodes/implement_task.py` (modified)
  - `scripts/init.sh` (modified)
  - `tests/test_boundaries.py` (new)
  - `tests/test_worktree.py` (new)
  - `shared-rules/agent-overrides/claude.md` (updated)
  - `shared-rules/cli-reference.md` (updated)
  - `shared-rules/guardrails.md` (updated)

### 2026-01-21 - Simplified Project Workflow

- **Issue**: Complex templating system with multiple project types, version tracking, and sync mechanisms added unnecessary complexity
- **Root Cause**: Over-engineering for hypothetical future needs
- **Fix**: Simplified to minimal workflow:
  - Projects initialized with just Documents/, .workflow/, and .project-config.json
  - User provides context files (CLAUDE.md, GEMINI.md, .cursor/rules) pre-researched for their project
  - No templates, no version tracking, no sync mechanisms
  - Projects are self-contained with their own git repos
- **Prevention**:
  - Start simple, add complexity only when needed
  - Let users bring their own context rather than generating it
  - Focus on workflow orchestration, not project scaffolding
- **Applies To**: all
- **Files Changed**:
  - Removed: project-templates/, VERSION, CHANGELOG.md
  - Removed: create-project.py, sync-project-templates.py, check-updates.py
  - Removed: update_manager.py, __version__.py
  - Simplified: init.sh, orchestrator.py, project_manager.py

### 2026-01-21 - Ralph Wiggum Loop for TDD Implementation

- **Issue**: Single-shot implementation sometimes fails on complex tasks, requiring full restart
- **Root Cause**: Context degradation during long implementations; no iterative retry mechanism
- **Fix**: Implemented Ralph Wiggum loop pattern:
  - Iterative execution until tests pass (fresh context each iteration)
  - Completion signal: `<promise>DONE</promise>`
  - Auto-detection: uses Ralph loop when `test_files` are defined
  - Configurable via `USE_RALPH_LOOP` environment variable
- **Prevention**:
  - Use Ralph loop for TDD tasks where tests already exist
  - Fresh context per iteration avoids token limit issues
  - Tests provide natural backpressure and completion signal
- **Applies To**: claude
- **Files Changed**:
  - `orchestrator/langgraph/integrations/ralph_loop.py` (new)
  - `orchestrator/langgraph/nodes/implement_task.py` (modified)
  - `tests/test_ralph_loop.py` (new)

### 2026-01-21 - Task-Based Incremental Execution

- **Issue**: One-shot implementation risky for larger features; failures mean redo everything
- **Root Cause**: No incremental verification; no progress visibility for stakeholders
- **Fix**: Implemented task-based execution:
  - Break PRODUCT.md into user stories/tasks via `task_breakdown` node
  - Implement task-by-task in a loop with verification after each
  - Task selection respects dependencies and priorities
  - Optional Linear integration for project tracking
- **Prevention**:
  - Always break features into discrete tasks with clear acceptance criteria
  - Verify each task before moving to next
  - Use dependency tracking to ensure correct execution order
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/langgraph/state.py` (Task, Milestone types)
  - `orchestrator/langgraph/nodes/task_breakdown.py` (new)
  - `orchestrator/langgraph/nodes/select_task.py` (new)
  - `orchestrator/langgraph/nodes/implement_task.py` (new)
  - `orchestrator/langgraph/nodes/verify_task.py` (new)
  - `orchestrator/langgraph/routers/task.py` (new)
  - `orchestrator/langgraph/integrations/linear.py` (new)
  - `tests/test_task_nodes.py` (new)
  - `tests/test_linear_integration.py` (new)

### 2026-01-21 - LangGraph Workflow Architecture

- **Issue**: Need for native parallelism, checkpointing, and human-in-the-loop without custom state management
- **Root Cause**: Original subprocess-based orchestration lacked proper parallel execution and resume capabilities
- **Fix**: Implemented LangGraph StateGraph with:
  - Parallel fan-out/fan-in for Cursor + Gemini (read-only)
  - Sequential implementation node (single writer prevents conflicts)
  - `interrupt()` for human escalation when worker needs clarification
  - SqliteSaver for checkpoint/resume
  - State reducers for merging parallel results
- **Prevention**:
  - Always keep file-writing operations sequential
  - Use state reducers (Annotated types) for parallel merge operations
  - Implement clarification flow for ambiguous requirements
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/langgraph/workflow.py`
  - `orchestrator/langgraph/state.py`
  - `orchestrator/langgraph/nodes/*.py`
  - `orchestrator/langgraph/routers/*.py`
  - `tests/test_langgraph.py`

### 2026-01-20 - CLI Flag Corrections

- **Issue**: Agent CLI commands were using wrong flags
- **Root Cause**: Assumed CLI syntax without verifying documentation
- **Fix**: Updated all agent wrappers with correct flags:
  - `cursor-agent`: Use `--print` for non-interactive, prompt is positional
  - `gemini`: Use `--yolo` for auto-approve, no `--output-format` flag
  - `claude`: Use `-p` followed by prompt, `--output-format json` works
- **Prevention**: Always verify CLI tool flags before implementing. Check `--help` or documentation.
- **Applies To**: all
- **Files Changed**:
  - `orchestrator/agents/cursor_agent.py`
  - `orchestrator/agents/gemini_agent.py`
  - `scripts/call-cursor.sh`
  - `scripts/call-gemini.sh`

---

## Lesson Template

```markdown
### YYYY-MM-DD - Brief Title

- **Issue**: What went wrong or was discovered
- **Root Cause**: Why it happened
- **Fix**: How it was fixed
- **Prevention**: Rule or check to prevent recurrence
- **Applies To**: all | claude | cursor | gemini
- **Files Changed**: List of affected files
```

---

## Archived Lessons

<!-- Move lessons here after 30 days or when the list gets too long -->
<!-- Keep for historical reference -->
