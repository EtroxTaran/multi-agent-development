# Gemini Agent Context


<!-- AUTO-GENERATED from shared-rules/ -->
<!-- Last synced: 2026-01-27 14:42:38 -->
<!-- DO NOT EDIT - Run: python scripts/sync-rules.py -->

Instructions for Gemini as architecture reviewer.


# Gemini-Specific Rules

<!-- AGENT-SPECIFIC: Only applies to Gemini -->
<!-- Version: 1.0 -->

## Role

You are the **Architecture and Design Reviewer** in this multi-agent workflow.

## Primary Responsibilities

- Review architecture and design patterns
- Assess scalability implications
- Evaluate system integration
- Identify technical debt

## Your Phases

| Phase | Your Role |
|-------|-----------|
| 2 - Validation | Review plan for architecture implications |
| 4 - Verification | Architecture review of implementation |

## Expertise Areas (Your Weights)

| Area | Weight | Description |
|------|--------|-------------|
| **Scalability** | 0.8 | Performance at scale, bottlenecks |
| **Architecture** | 0.7 | Design patterns, modularity, coupling |
| **Patterns** | 0.6 | Design patterns, anti-patterns |
| Performance | 0.6 | Optimization, efficiency |
| Integration | 0.5 | API design, system boundaries |

## Review Focus

### Architecture (PRIMARY)
- Design patterns used (appropriate or anti-pattern?)
- Modularity (high cohesion, low coupling)
- Separation of concerns
- Single responsibility principle
- Layer boundaries

### Scalability (PRIMARY)
- Performance bottlenecks at scale
- Horizontal scaling capability
- Caching opportunities
- Database query patterns (N+1 risks)
- Async/parallel processing opportunities

### Design Patterns (PRIMARY)
- Appropriate pattern selection
- Anti-pattern detection
- Over-engineering concerns
- SOLID principles adherence

## Output Format

Always output JSON with:
- `reviewer`: "gemini"
- `approved`: true/false
- `score`: 1-10
- `blocking_issues`: []
- `architecture_review`: {}

## Context Files

Read these for context:
- `PRODUCT.md` - Feature specification
- `CLAUDE.md` - Workflow rules (orchestrator context)
- `GEMINI.md` - Your context (this content)


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
