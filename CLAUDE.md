# Claude Code Context


<!-- AUTO-GENERATED from shared-rules/ -->
<!-- Last synced: 2026-01-27 14:42:38 -->
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


## Slash Commands

**40 skills available.** Run `/skills` for full list with descriptions.


**Workflow**: `/git-workflow-helper`, `/implement-task`, `/orchestrate`, `/phase-status`, `/plan`, `/plan-feature`...
**Git & PRs**: `/git-commit-conventional`, `/git-committer-atomic`, `/github-actions-debugging`, `/list-projects`, `/pr-create`, `/release-notes-and-changelog`, `/review-pr`
**Code Quality**: `/api-contracts-and-validation`, `/e2e-webapp-testing`, `/frontend-dev-guidelines`, `/test-writer-unit-integration`, `/ts-strict-guardian`...
**Debugging**: `/debug`


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
- Query `workflow_state` from SurrealDB before starting work
- Update workflow state in SurrealDB after completing each phase
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
- Query SurrealDB `workflow_state` table for current state

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
<!-- Version: 2.1 -->
<!-- Last Updated: 2026-01-27 -->

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

## Input Validation Guardrails

**Use the `orchestrator.security` module for all input validation.**

### SQL Identifiers

All table and field names must be validated against allowlists before use in queries.

```python
from orchestrator.security import validate_sql_table, validate_sql_field

# Always validate before query construction
validated_table = validate_sql_table(table_name)
validated_field = validate_sql_field(field_name)
await conn.query(f"INFO FOR TABLE {validated_table}")
```

### Never Do
- Interpolate unvalidated identifiers into SQL queries
- Add new tables without updating `ALLOWED_TABLES`
- Use string concatenation for SQL construction

### Command Execution

All shell commands must use list-form execution to prevent injection.

```python
import subprocess
import shlex
from orchestrator.security import validate_package_name, validate_file_path

# For package installation - validate first
validated_pkg = validate_package_name(package)
subprocess.run(["pip", "install", validated_pkg], shell=False)

# For file operations - validate path
validated_path = validate_file_path(user_path, base_dir)
subprocess.run(["autopep8", "--in-place", validated_path], shell=False)

# For arbitrary commands - use shlex.split
cmd_parts = shlex.split(command_string)
subprocess.run(cmd_parts, shell=False)
```

### Never Do
- Use `shell=True` with dynamic input
- Interpolate user input directly into command strings
- Trust package names without validation

### Prompt Construction

User-provided content must be sanitized before inclusion in LLM prompts.

```python
from orchestrator.security import sanitize_prompt_content, detect_prompt_injection
from orchestrator.agents.prompts import format_prompt

# Check for injection patterns
suspicious = detect_prompt_injection(user_content)
if suspicious:
    logger.warning(f"Potential injection: {suspicious}")

# Sanitize with boundaries
sanitized = sanitize_prompt_content(
    user_content,
    max_length=50000,
    validate_injection=True,
    boundary_markers=True,
)

# Use format_prompt with validation enabled
prompt = format_prompt(template, validate_injection=True, content=user_content)
```

### Never Do
- Insert raw user content directly into prompts
- Skip injection detection for external content
- Ignore warnings about detected injection patterns

### Always Do
- Wrap user content with boundary markers
- Add defensive instructions after user content
- Truncate overly long content

### Shell Scripts

Shell scripts must follow safe quoting practices.

```bash
# Always quote variables
echo "$VARIABLE"

# Use arrays for multi-word arguments
ARGS=("--flag1" "value with spaces")
command "${ARGS[@]}"

# Use single quotes in traps
trap 'rm -f "$TEMP_FILE"' EXIT

# Check file safety before reading
if [ -L "$FILE" ]; then
    echo "Error: symlink" >&2
    exit 1
fi
```

### Never Do
- Leave variables unquoted
- Use string variables for multi-argument options
- Use double quotes in trap commands with variables

---

## Orchestrator Storage Guardrails

**See `shared-rules/agent-overrides/claude.md` for full storage architecture details.**

Key rules:
- **SurrealDB only** - No local file storage for workflow state
- **Never write code** - Spawn worker Claude instead
- **Verify DB** - Check `SURREAL_URL` before workflow starts

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
<!-- Version: 3.0 -->
<!-- Last Updated: 2026-01-27 -->

## Quick Reference Table

| Tool | Non-Interactive | Prompt | Output Format |
|------|-----------------|--------|---------------|
| `claude` | `-p "prompt"` | Part of `-p` | `--output-format json` |
| `cursor-agent` | `--print` | Positional (end) | `--output-format json` |
| `gemini` | `--yolo` | Positional | N/A (wrap externally) |

---

## Claude Code CLI

**Command**: `claude -p "prompt" --output-format json`

### Key Flags
| Flag | Purpose |
|------|---------|
| `-p` | Prompt (non-interactive) |
| `--output-format` | Output format (json) |
| `--allowedTools` | Restrict tools |
| `--permission-mode plan` | Plan before implementing |
| `--resume <session-id>` | Continue previous session |
| `--max-budget-usd <n>` | Limit API cost |
| `--fallback-model <model>` | Failover model (sonnet/haiku) |

### Decision Matrix

| Scenario | Plan Mode | Session | Budget |
|----------|-----------|---------|--------|
| Simple 1-2 file task | No | No | $0.50 |
| Multi-file (≥3 files) | Yes | No | $1.00 |
| High complexity | Yes | No | $2.00 |
| Ralph loop iteration 1 | No | New | $0.50 |
| Ralph loop iteration 2+ | No | Resume | $0.50 |

---

## Cursor Agent CLI

**Command**: `cursor-agent --print --output-format json "prompt"`

- `--print` or `-p`: Non-interactive mode
- Prompt is POSITIONAL (at the END)
- Common mistake: `-p "prompt"` is wrong (means `--print`)

---

## Gemini CLI

**Command**: `gemini --yolo "prompt"`

- `--yolo`: Auto-approve tool calls
- `--model`: Select model (gemini-2.0-flash)
- Does NOT support `--output-format`
- Prompt is positional

---

## Python Orchestrator

**Command**: `python -m orchestrator`

### Key Flags
| Flag | Purpose |
|------|---------|
| `--project <name>` | Nested project name |
| `--project-path <path>` | External project path |
| `--start` | Start workflow |
| `--resume` | Resume from checkpoint |
| `--status` | Show workflow status |
| `--autonomous` | Run without human input |

---

## Shell Script (init.sh)

```bash
./scripts/init.sh init <name>     # Initialize project
./scripts/init.sh run <name>      # Run workflow
./scripts/init.sh run --path <p>  # External project
./scripts/init.sh status <name>   # Check status
```

---

## Environment Variables

```bash
export ORCHESTRATOR_USE_LANGGRAPH=true  # LangGraph mode
export USE_RALPH_LOOP=auto              # TDD loop (auto|true|false)
export PARALLEL_WORKERS=3               # Parallel workers
```

---

## Autonomous Decision Guidelines

**DO automatically:**
- Use plan mode for ≥3 files or high complexity
- Resume sessions for Ralph iterations 2+
- Set budget limits on all invocations

**DO NOT without asking:**
- Skip budget limits entirely
- Change project-wide budget limits

---

**For detailed examples, see `shared-rules/cli-examples.md`.**

---

# Lessons Learned

<!-- SHARED: This file applies to ALL agents -->
<!-- Add new lessons at the TOP of this file -->
<!-- Version: 2.0 -->
<!-- Last Updated: 2026-01-27 -->

## How to Add a Lesson

When you discover a bug, mistake, or pattern that should be remembered:

1. Add a new entry at the TOP of the "Recent Lessons" section
2. Follow the template format
3. Run `python scripts/sync-rules.py` to propagate

**Note**: Older lessons are archived in `shared-rules/lessons-archived.md`.

---

## Recent Lessons (Last 5)

### 2026-01-23 - Global Bugfixer and Optimizer Agents

- **Issue**: Bugfixer only caught ~30% of errors (8 nodes had no error routing), Optimizer only evaluated ~10% of agent executions
- **Root Cause**: Error handling and evaluation were implemented ad-hoc per node instead of as universal infrastructure
- **Fix**: Implemented comprehensive global agent infrastructure with `@wrapped_node` decorator, `ErrorContext` TypedDict, `AgentExecution` tracking, and template-specific evaluation criteria for all 9 templates
- **Prevention**: Use `@wrapped_node` decorator for ALL new nodes; use `create_agent_execution()` helper when calling agents; all errors route through `error_dispatch` node
- **Applies To**: all

### 2026-01-23 - Web Search for Research Agents and HITL User Input

- **Issue**: Research agents relied solely on codebase analysis; workflow interrupts had no interactive CLI for human input
- **Root Cause**: No web search capability; non-interactive mode meant users couldn't respond to escalations
- **Fix**: Implemented web research agent with `ResearchConfig` and interactive HITL CLI with `UserInputManager` for escalation/approval handling
- **Prevention**: Use `ResearchConfig` for web tool configuration; use `UserInputManager.handle_interrupt()` for HITL processing; test for `is_interactive()` before prompting
- **Applies To**: all

### 2026-01-23 - Dynamic Role Dispatch for Task-Aware Agent Selection

- **Issue**: Conflict resolution between Cursor and Gemini used static weights (0.6/0.4), ignoring task context
- **Root Cause**: All tasks treated equally regardless of security vs architecture focus
- **Fix**: Implemented Dynamic Role Dispatch with `infer_task_type()` and role-based weights (SECURITY: Cursor 0.8, ARCHITECTURE: Gemini 0.7)
- **Prevention**: Use `infer_task_type()` before conflict resolution; pass role weights to `resolver.resolve()`
- **Applies To**: all

### 2026-01-23 - Full SurrealDB Migration - Remove File-Based Storage

- **Issue**: Workflow state in `.workflow/` files caused state management issues and debugging difficulties
- **Root Cause**: Original design used local files as fallback, but this was unnecessary since AI agents require network anyway
- **Fix**: Complete migration to SurrealDB with new `phase_outputs` and `logs` tables, removed file fallback from all adapters
- **Prevention**: Never add file-based fallback for workflow state; use storage adapters and repositories; validate DB connection at startup
- **Applies To**: all

### 2026-01-22 - Native Claude Code Skills Architecture for Token Efficiency

- **Issue**: Python-based orchestration spawning Claude via subprocess was token-inefficient (~13k overhead per spawn)
- **Root Cause**: Subprocess spawning duplicates full context to each worker
- **Fix**: Implemented skills in `.claude/skills/` using Task tool for 70% token savings; Bash for external agents
- **Prevention**: Always prefer Task tool over subprocess; use Skills for reusable patterns; use Bash for external CLI agents
- **Applies To**: claude

---

## Lesson Template

```markdown
### YYYY-MM-DD - Brief Title

- **Issue**: What went wrong or was discovered
- **Root Cause**: Why it happened
- **Fix**: How it was fixed
- **Prevention**: Rule or check to prevent recurrence
- **Applies To**: all | claude | cursor | gemini
```

---

## Archived Lessons

Older lessons (9 entries from 2026-01-20 to 2026-01-22) are in `shared-rules/lessons-archived.md`.
