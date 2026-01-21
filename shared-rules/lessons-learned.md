# Lessons Learned

<!-- SHARED: This file applies to ALL agents -->
<!-- Add new lessons at the TOP of this file -->
<!-- Version: 1.2 -->
<!-- Last Updated: 2026-01-21 -->

## How to Add a Lesson

When you discover a bug, mistake, or pattern that should be remembered:

1. Add a new entry at the TOP of the "Recent Lessons" section
2. Follow the template format
3. Run `python scripts/sync-rules.py` to propagate

---

## Recent Lessons

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
