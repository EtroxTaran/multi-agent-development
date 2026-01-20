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
