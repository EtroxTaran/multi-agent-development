# Claude Code Context


<!-- AUTO-GENERATED from shared-rules/ -->
<!-- Last synced: 2026-01-21 19:49:11 -->
<!-- DO NOT EDIT - Run: python scripts/sync-rules.py -->

Instructions for Claude Code as lead orchestrator.


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
- Always read AGENTS.md for workflow rules
- Always read PRODUCT.md for requirements
- Check .workflow/state.json for current state

## Error Handling

### When Errors Occur
- Log the error clearly with context
- Suggest remediation steps
- Don't proceed with broken state
- Update blockers.md if blocked

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

### JavaScript/TypeScript
- Use const/let, never var
- Prefer async/await over raw promises
- Use TypeScript for new code when possible
- Prefer named exports over default exports

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

## Orchestrator File Boundary Guardrails

**These rules apply specifically to the orchestrator (Claude as lead orchestrator).**

### Orchestrator CAN Write To
```
projects/<name>/.workflow/**         <- Workflow state, phase outputs
projects/<name>/.project-config.json <- Project configuration
```

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
- Modify files outside `.workflow/` directory
- Change project context files (CLAUDE.md, GEMINI.md)
- Bypass boundary validation with direct file writes

### Always Do (Orchestrator)
- Use `safe_write_workflow_file()` for workflow state
- Use `safe_write_project_config()` for configuration
- Spawn worker Claude for any code changes
- Validate paths before writing

### Error Recovery
If you see `OrchestratorBoundaryError`:
1. Check that you're writing to `.workflow/` or `.project-config.json`
2. Use the safe write methods in ProjectManager
3. If code changes are needed, spawn a worker Claude

---

## Code Quality Guardrails

### Never Do
- Leave debug code (console.log, print, debugger)
- Commit commented-out code
- Create empty catch blocks
- Use magic numbers without constants
- Ignore linter/type errors

### Always Do
- Run tests before marking complete
- Check for regressions in existing tests
- Follow existing code patterns
- Clean up temporary files

---

## Workflow Guardrails

### Never Do
- Skip phases in the workflow
- Proceed without required approvals
- Ignore blocking issues
- Mark tasks complete when they're not

### Always Do
- Update state.json after phase transitions
- Document decisions in decisions.md
- Write handoff notes for session resumption
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

### Never Do
- Assume external projects have same structure as nested
- Run workflow without validating PRODUCT.md first
- Modify files outside expected locations

### Always Do
- Use `--project-path` flag for external projects
- Validate project structure before starting workflow
- Create `.workflow/` directory if missing

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

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `-p` | Prompt (non-interactive) | `-p "What is 2+2?"` |
| `--output-format` | Output format | `--output-format json` |
| `--allowedTools` | Restrict tools | `--allowedTools "Read,Write,Edit"` |
| `--max-turns` | Limit turns | `--max-turns 10` |

### Full Example
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
export CURSOR_MODEL=gpt-4.5-turbo    # Override Cursor model
export GEMINI_MODEL=gemini-2.0-flash  # Override Gemini model
```

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
<!-- Version: 1.3 -->
<!-- Last Updated: 2026-01-21 -->

## How to Add a Lesson

When you discover a bug, mistake, or pattern that should be remembered:

1. Add a new entry at the TOP of the "Recent Lessons" section
2. Follow the template format
3. Run `python scripts/sync-rules.py` to propagate

---

## Recent Lessons

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