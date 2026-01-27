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
