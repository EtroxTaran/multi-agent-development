# Documentation Index

## Current Documentation

| Document | Description |
|----------|-------------|
| [Quick Start](quick-start.md) | Step-by-step guide to create and run your first project |
| [README.md](../README.md) | Complete system reference with architecture details |
| [CLAUDE.md](../CLAUDE.md) | Claude orchestrator context with full feature documentation |

## Key Concepts

### Architecture
- **Nested Architecture**: Projects live in `projects/<name>/` with isolated context
- **External Project Mode**: Run workflow on any directory with `--project-path`
- **File Boundaries**: Orchestrator can only write to `.workflow/` and `.project-config.json`
- **Two-Layer Context**: Outer (orchestrator rules) vs Inner (worker coding rules)

### Workflow
- **LangGraph Workflow**: Graph-based orchestration with parallel execution
- **5-Phase Process**: Planning -> Validation -> Implementation -> Verification -> Completion
- **Task-Based Execution**: Features broken into tasks with incremental verification
- **Parallel Workers**: Independent tasks can run in parallel using git worktrees

### Safety Features
- **Boundary Enforcement**: `OrchestratorBoundaryError` prevents writing to app code
- **Scoped Prompts**: Workers receive minimal context for their specific task
- **Worktree Isolation**: Parallel workers operate in isolated git worktrees
- **Auto-Cleanup**: Worktrees automatically cleaned up after execution

## Quick Reference

### Project Modes

```bash
# Nested project (in projects/ directory)
./scripts/init.sh init my-app
./scripts/init.sh run my-app

# External project (any directory)
./scripts/init.sh run --path ~/repos/my-project

# Parallel workers (experimental)
./scripts/init.sh run my-app --parallel 3
```

### File Boundary Rules

| Path | Orchestrator | Worker |
|------|--------------|--------|
| `.workflow/**` | Write | Read |
| `.project-config.json` | Write | Read |
| `src/**` | Read-only | Write |
| `tests/**` | Read-only | Write |
| `CLAUDE.md` | Read-only | Read |
| `PRODUCT.md` | Read-only | Read |

### CLI Reference

See [shared-rules/cli-reference.md](../shared-rules/cli-reference.md) for complete CLI documentation.

## Shared Rules

The `shared-rules/` directory contains the single source of truth for all agent rules:

| File | Description |
|------|-------------|
| `core-rules.md` | Fundamental workflow rules |
| `coding-standards.md` | Code patterns, style, conventions |
| `guardrails.md` | Safety and quality guardrails |
| `cli-reference.md` | Correct CLI tool usage |
| `lessons-learned.md` | Historical fixes and learnings |
| `agent-overrides/` | Agent-specific additions |

Run `python scripts/sync-rules.py` to regenerate agent context files from shared rules.

## Archived Documentation

Historical documents from earlier development phases (pre-LangGraph):

- [archive/](archive/) - Contains:
  - `delivery-package.md` - Original delivery documentation
  - `orchestrator-impl.md` - Pre-LangGraph implementation details
  - `unified-multi-cli-orchestration.md` - Research artifact for multi-CLI coordination
  - `multi-agent-guide.md` - Pre-LangGraph multi-agent guide
  - `implementation-guide.md` - Legacy phase-based implementation guide

These archived documents are kept for historical reference but do not reflect
the current LangGraph-based workflow architecture.
