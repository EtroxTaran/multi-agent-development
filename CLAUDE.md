# Claude Code Context


<!-- AUTO-GENERATED from shared-rules/ -->
<!-- Last synced: 2026-01-21 00:31:16 -->
<!-- DO NOT EDIT - Run: python scripts/sync-rules.py -->

Instructions for Claude Code as lead orchestrator.


# Claude-Specific Rules

<!-- AGENT-SPECIFIC: Only applies to Claude -->
<!-- Version: 2.0 -->
<!-- Updated: 2026-01-20 - Nested orchestration architecture -->

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
<!-- Version: 1.0 -->
<!-- Last Updated: 2026-01-20 -->

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

# CLI Reference (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 1.0 -->
<!-- Last Updated: 2026-01-20 -->

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

### Commands
```bash
# Start new workflow
python -m orchestrator --start

# Resume interrupted workflow
python -m orchestrator --resume

# Check health/prerequisites
python -m orchestrator --health

# Initialize missing files
python -m orchestrator --init
```

---

## Shell Script Wrappers

### call-cursor.sh
```bash
bash scripts/call-cursor.sh <prompt-file> <output-file> [project-dir]
```

### call-gemini.sh
```bash
bash scripts/call-gemini.sh <prompt-file> <output-file> [project-dir]
```

### Environment Variables
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

# Lessons Learned

<!-- SHARED: This file applies to ALL agents -->
<!-- Add new lessons at the TOP of this file -->
<!-- Version: 1.0 -->
<!-- Last Updated: 2026-01-20 -->

## How to Add a Lesson

When you discover a bug, mistake, or pattern that should be remembered:

1. Add a new entry at the TOP of the "Recent Lessons" section
2. Follow the template format
3. Run `python scripts/sync-rules.py` to propagate

---

## Recent Lessons

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