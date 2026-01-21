# Claude-Specific Rules

<!-- AGENT-SPECIFIC: Only applies to Claude -->
<!-- Version: 2.3 -->
<!-- Updated: 2026-01-21 - Added Project Update Mechanism with Versioning -->

---

## 🚀 Quick Start - When User Has a Product Vision

**If the user says they have a product idea or feature to build, follow these steps:**

### Step 1: Create the Project
```bash
./scripts/init.sh create <project-name> --type <type>
```

Project types: `node-api` | `react-tanstack` | `java-spring` | `nx-fullstack`

### Step 2: User Provides PRODUCT.md
Ask the user to either:
- Paste their product vision/requirements, OR
- Confirm you should read their existing `projects/<name>/PRODUCT.md`

Then write/update `projects/<name>/PRODUCT.md` with these required sections:
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
1. ✅ Validate PRODUCT.md (must score ≥6.0)
2. 📋 Create implementation plan
3. 🔍 Cursor + Gemini validate the plan
4. 💻 Worker Claude implements with TDD
5. 🔒 Security scan and coverage check
6. ✅ Cursor + Gemini verify the code
7. 📄 Generate completion summary

---

## Role

You are the **Lead Orchestrator** in this multi-agent workflow. You coordinate agents and manage workflow phases.

**CRITICAL: You are the ORCHESTRATOR. You NEVER write application code directly.**

## Nested Architecture

This system uses a two-layer nested architecture:

```
meta-architect/                     ← OUTER LAYER (You - Orchestrator)
├── CLAUDE.md                       ← Your context (workflow rules)
├── orchestrator/                   ← Python orchestration module
├── scripts/                        ← Agent invocation scripts
└── projects/                       ← Project containers
    └── <project-name>/             ← INNER LAYER (Worker Claude)
        ├── CLAUDE.md               ← Worker context (coding rules)
        ├── PRODUCT.md              ← Feature specification
        ├── .workflow/              ← Project workflow state
        ├── src/                    ← Application source code
        └── tests/                  ← Application tests
```

## Primary Responsibilities

1. **Manage Projects**: Create, list, and track projects in `projects/`
2. **Read Specifications**: Read `projects/<name>/PRODUCT.md`
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
# Create new project
python scripts/create-project.py <project-name> [--template base]

# List projects
python scripts/create-project.py --list

# Sync templates to projects
python scripts/sync-project-templates.py --all
python scripts/sync-project-templates.py --project <name>
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
- `/create-project <name>` - Create new project from template
- `/sync-projects` - Sync template updates to projects
- `/phase-status --project <name>` - Show project workflow status
- `/list-projects` - List all projects
- `/check-updates --project <name>` - Check for available updates
- `/update-project --project <name>` - Apply updates with backup

---

## LangGraph Workflow Architecture

The orchestration system uses LangGraph for graph-based workflow management with native parallelism and checkpointing.

### Workflow Graph Structure

```
┌──────────────────┐
│  prerequisites   │ ← Check project setup, load PRODUCT.md
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│    planning      │ ← Create plan.json (Phase 1)
└────────┬─────────┘
         │
    ┌────┴────┐ (parallel fan-out)
    ▼         ▼
┌────────┐ ┌────────┐
│ cursor │ │ gemini │ ← Validate plan (Phase 2)
│validate│ │validate│   READ-ONLY - no file writes
└───┬────┘ └───┬────┘
    │         │
    └────┬────┘ (parallel fan-in)
         ▼
┌──────────────────┐
│validation_fan_in │ ← Merge feedback, decide routing
└────────┬─────────┘
         │
         ▼ (conditional)
┌──────────────────┐
│ implementation   │ ← Worker Claude writes code (Phase 3)
└────────┬─────────┘   SEQUENTIAL - single writer
         │
    ┌────┴────┐ (parallel fan-out)
    ▼         ▼
┌────────┐ ┌────────┐
│ cursor │ │ gemini │ ← Review code (Phase 4)
│ review │ │ review │   READ-ONLY - no file writes
└───┬────┘ └───┬────┘
    │         │
    └────┬────┘ (parallel fan-in)
         ▼
┌──────────────────┐
│verification_fan_in│ ← Merge reviews, decide routing
└────────┬─────────┘
         │
         ▼ (conditional)
┌──────────────────┐
│   completion     │ ← Generate summary (Phase 5)
└──────────────────┘
```

### Safety Guarantees

1. **Sequential File Writing**: Only the `implementation` node writes files. Cursor and Gemini are read-only reviewers.
2. **Human Escalation**: When max retries exceeded or worker needs clarification, workflow pauses via `interrupt()` for human input.
3. **State Persistence**: SqliteSaver enables checkpoint/resume from any point.
4. **Transient Error Recovery**: Exponential backoff with jitter for recoverable errors.

### Worker Clarification Flow

When the implementation worker encounters ambiguity:

1. Worker outputs `status: "needs_clarification"` with question
2. Implementation node detects this and sets `next_decision: "escalate"`
3. Router sends to `human_escalation` node
4. `interrupt()` pauses workflow with clarification context
5. Human answers via `Command(resume={"action": "answer_clarification", "answers": {...}})`
6. Answers saved to `.workflow/clarification_answers.json`
7. Workflow retries implementation with answers in prompt

### State Schema

```python
class WorkflowState(TypedDict):
    project_dir: str
    project_name: str
    current_phase: int
    phase_status: dict[str, PhaseState]  # "1"-"5" → PhaseState
    iteration_count: int
    plan: Optional[dict]
    validation_feedback: Annotated[dict, _merge_feedback]  # Parallel merge
    verification_feedback: Annotated[dict, _merge_feedback]
    implementation_result: Optional[dict]
    next_decision: Optional[WorkflowDecision]  # continue|retry|escalate|abort
    errors: Annotated[list[dict], operator.add]  # Append-only
    checkpoints: list[str]
    git_commits: list[dict]
    created_at: str
    updated_at: Annotated[str, _latest_timestamp]
```

### Running with LangGraph

```bash
# Run new workflow
python -m orchestrator --project <name> --use-langgraph

# Resume from checkpoint
python -m orchestrator --project <name> --resume --use-langgraph

# Run tests
python -m pytest tests/test_langgraph.py -v
```

### Key Files

| File | Purpose |
|------|---------|
| `orchestrator/langgraph/workflow.py` | Graph assembly, entry point |
| `orchestrator/langgraph/state.py` | TypedDict state schema, reducers |
| `orchestrator/langgraph/nodes/*.py` | Node implementations |
| `orchestrator/langgraph/routers/*.py` | Conditional edge logic |
| `orchestrator/langgraph/integrations/*.py` | Adapters for existing utils |

---

## Task-Based Incremental Execution

Instead of implementing the entire feature in one shot, the workflow breaks PRODUCT.md into individual tasks and implements them one-by-one with verification after each.

### Task Loop Structure

```
planning → task_breakdown →
    ┌─────────────────────────────────────────┐
    │            TASK LOOP                    │
    │  select_task → implement_task →         │
    │       ↑         verify_task ────────────┼──┐
    │       └─────────────────────────────────┘  │
    │              (loop back)                   │
    └────────────────────────────────────────────┘
                        │ (all tasks complete)
                        ↓
                build_verification → ...
```

### Task Data Model

```python
class Task(TypedDict):
    id: str                          # "T1", "T2"
    title: str                       # Short title
    user_story: str                  # "As a... I want... So that..."
    acceptance_criteria: list[str]   # Checklist items
    dependencies: list[str]          # Task IDs this depends on
    status: TaskStatus               # pending|in_progress|completed|failed|blocked
    priority: str                    # critical|high|medium|low
    files_to_create: list[str]
    files_to_modify: list[str]
    test_files: list[str]
    attempts: int
    max_attempts: int                # Default 3
```

### Task Selection Algorithm

1. Filter tasks with `status == "pending"`
2. Filter tasks with all dependencies in `completed_task_ids`
3. Sort by: priority (high first) → milestone order → task ID
4. Select first available task

### Benefits

- **Incremental verification**: Catch issues early, not after hours of work
- **Progress visibility**: Track completion percentage
- **Safer rollback**: Revert individual tasks, not entire feature
- **Linear integration**: Optionally sync tasks to Linear issues

---

## Ralph Wiggum Loop (TDD Mode)

The Ralph Wiggum loop is an iterative execution pattern for TDD-based implementation. When tests already exist, it runs Claude in a loop until all tests pass.

### How It Works

```
┌─────────────────┐
│  Task Selected  │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Tests   │
    │ exist?  │
    └────┬────┘
   YES   │   NO
    ┌────┴────────────┐
    │ Ralph Loop      │ Standard Mode
    └────┬────────────┘
         │
    ┌────┴────┐
    │ Fresh   │
    │ Claude  │ (iteration 1)
    └────┬────┘
         │
    ┌────┴────┐
    │ Tests   │
    │ Pass?   │
    └────┬────┘
   YES   │   NO (spawn new Claude, loop)
         │
    ┌────┴────┐
    │ Done!   │
    └─────────┘
```

### Key Principles

1. **Fresh context each iteration**: Avoids context degradation on complex tasks
2. **Tests as backpressure**: Natural completion signal (all tests green)
3. **Completion promise**: `<promise>DONE</promise>` signals task complete
4. **Automatic retry**: Keeps iterating until tests pass (up to 10 iterations)

### Configuration

```bash
# Enable Ralph loop for all tasks
USE_RALPH_LOOP=true python -m orchestrator --project my-project

# Disable Ralph loop (use standard single-invocation mode)
USE_RALPH_LOOP=false python -m orchestrator --project my-project

# Auto-detect (default): use Ralph if task has test_files defined
USE_RALPH_LOOP=auto python -m orchestrator --project my-project
```

### When to Use Ralph Loop

| Scenario | Recommendation |
|----------|----------------|
| Tests already exist (TDD) | ✅ Use Ralph loop |
| Complex multi-step task | ✅ Use Ralph loop |
| Simple single-file change | ❌ Use standard mode |
| No tests defined | ❌ Use standard mode |

### Iteration Logs

Ralph loop saves logs to `.workflow/ralph_logs/{task_id}/`:
- `iteration_001.json` - First iteration metadata
- `iteration_002.json` - Second iteration metadata
- etc.

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
      "create_project": true,
      "status_mapping": {
        "pending": "Backlog",
        "in_progress": "In Progress",
        "completed": "Done",
        "blocked": "Blocked",
        "failed": "Cancelled"
      }
    }
  }
}
```

### MCP Setup

Linear integration uses the official Linear MCP. Add to `mcp.json`:

```json
{
  "mcp-linear": {
    "command": "npx",
    "args": ["-y", "mcp-remote", "https://mcp.linear.app/mcp"],
    "description": "Official Linear MCP for issue tracking",
    "optional": true
  }
}
```

### What Gets Synced

| Workflow Event | Linear Action |
|----------------|---------------|
| Task breakdown | Create issues from tasks |
| Task started | Update status to "In Progress" |
| Task completed | Update status to "Done" |
| Task blocked | Add blocker comment |
| Task failed | Update status to "Cancelled" |

### Graceful Degradation

If Linear MCP is unavailable or not configured:
- Workflow continues normally
- No errors thrown
- Tasks tracked in `.workflow/` only

---

## Project Update Mechanism

Meta-architect includes a versioning and update system to keep projects in sync with the latest templates and features.

### Version Tracking

Each project tracks its meta-architect version in `.project-config.json`:

```json
{
  "versioning": {
    "meta_architect_version": "0.2.0",
    "last_sync_version": "0.2.0",
    "update_policy": "prompt"
  }
}
```

The current meta-architect version is stored in `VERSION` file at the repo root.

### Checking for Updates

```bash
# Check updates for a specific project
python -m orchestrator --project my-app --check-updates

# Check updates for all projects
python -m orchestrator --check-all-updates

# Or use slash command
/check-updates --project my-app
```

The check displays:
- Current version vs latest version
- Whether it's a breaking update (major version change)
- Changelog entries since current version
- Files that would be updated

### Applying Updates

```bash
# Apply updates (creates automatic backup)
python -m orchestrator --project my-app --update

# Dry run (preview changes)
python -m orchestrator --project my-app --update --dry-run

# Or use slash command
/update-project --project my-app
```

The update process:
1. Creates backup in `.workflow/backups/<timestamp>/`
2. Syncs templates from `project-templates/`
3. Preserves project-overrides/
4. Updates `.project-config.json` with new version

### Backup and Rollback

```bash
# List available backups
python -m orchestrator --project my-app --list-backups

# Rollback to a specific backup
python -m orchestrator --project my-app --rollback-backup 20260121_150000
```

### Update Policies

Projects can configure how updates are handled:

| Policy | Behavior |
|--------|----------|
| `auto` | Automatically apply non-breaking updates |
| `prompt` | Show notification, require explicit command (default) |
| `manual` | Never auto-check, user must explicitly run updates |

### What Gets Updated

| File | Updated | Notes |
|------|---------|-------|
| `CLAUDE.md` | Yes | Context rules from template |
| `GEMINI.md` | Yes | Context rules from template |
| `.cursor/rules` | Yes | Cursor context from template |
| `PRODUCT.md` | **No** | User content preserved |
| `.workflow/` | **No** | Workflow state preserved |
| `src/`, `tests/` | **No** | Application code preserved |
| `project-overrides/` | **No** | Custom overrides preserved |

### Git Repository Isolation

**Important**: Projects have their own git repositories separate from meta-architect.

```
meta-architect/                    ← Git repo #1 (orchestrator code)
├── .git/
├── projects/
│   └── my-app/                    ← Git repo #2 (project code)
│       ├── .git/                  ← Separate git history
│       └── CLAUDE.md              ← Tracked by project's git, NOT meta-architect
```

When you run `/update-project`:

| Action | What Happens |
|--------|--------------|
| Template source | Read from **meta-architect** templates |
| File changes | Written to project directory |
| Git tracking | Changes appear in **project's** `git status` |
| Meta-architect git | **Unaffected** - stays clean |
| Project's remote | **Never touched** - you push manually |

This means:
- Updates fetch from meta-architect's templates (local or via `git pull` on meta-architect)
- Your project's own GitHub/remote repository is never modified by update commands
- After updates, commit changes to your **project's** repo: `cd projects/my-app && git commit`

### CLI Quick Reference

```bash
# Update management
python -m orchestrator --project <name> --check-updates
python -m orchestrator --project <name> --update [--dry-run]
python -m orchestrator --check-all-updates
python -m orchestrator --project <name> --list-backups
python -m orchestrator --project <name> --rollback-backup <id>
```
