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
