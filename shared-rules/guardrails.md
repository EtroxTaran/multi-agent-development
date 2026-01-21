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
