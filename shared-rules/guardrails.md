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

## Orchestrator Storage Guardrails

**These rules apply specifically to the orchestrator (Claude as lead orchestrator).**

### Storage Architecture
All workflow state is stored in **SurrealDB** - there is no local file storage for workflow state.

### Orchestrator CAN
- Store workflow state in SurrealDB (via storage adapters)
- Read project files (Docs/, PRODUCT.md, CLAUDE.md)
- Spawn worker Claude for code changes

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
- Write workflow state to local files (use DB)
- Change project context files (CLAUDE.md, GEMINI.md)
- Run workflow without SurrealDB connection

### Always Do (Orchestrator)
- Use storage adapters for workflow state
- Use repositories for phase outputs and logs
- Spawn worker Claude for any code changes
- Verify DB connection before starting workflow

### Error Recovery
If you see `DatabaseRequiredError`:
1. Set `SURREAL_URL` environment variable
2. Verify SurrealDB instance is running
3. Check network connectivity to database

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
