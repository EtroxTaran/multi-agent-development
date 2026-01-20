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
