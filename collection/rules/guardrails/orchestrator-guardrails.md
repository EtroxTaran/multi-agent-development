---
name: Orchestrator Guardrails
tags:
  technology: [python]
  feature: [workflow, database]
  priority: critical
summary: Guardrails specific to the Conductor orchestrator including storage, workflow, and file operation rules
version: 1
---

# Orchestrator Guardrails

## Storage Architecture

All workflow state is stored in **SurrealDB** - there is no local file storage for workflow state.

## Orchestrator CAN
- Store workflow state in SurrealDB (via storage adapters)
- Read project files (Docs/, PRODUCT.md, CLAUDE.md)
- Spawn worker Claude for code changes

## Orchestrator CANNOT Write To
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

## Never Do (Orchestrator)
- Write application code directly (spawn workers instead)
- Write workflow state to local files (use DB)
- Change project context files (CLAUDE.md, GEMINI.md)
- Run workflow without SurrealDB connection

## Always Do (Orchestrator)
- Use storage adapters for workflow state
- Use repositories for phase outputs and logs
- Spawn worker Claude for any code changes
- Verify DB connection before starting workflow

## Error Recovery

If you see `DatabaseRequiredError`:
1. Set `SURREAL_URL` environment variable
2. Verify SurrealDB instance is running
3. Check network connectivity to database

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
