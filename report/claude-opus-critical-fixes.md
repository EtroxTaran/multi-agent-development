# Critical Fixes - Priority Action List

**Generated**: 2026-01-21
**Source**: Pre-Mortem Analysis by Claude Opus 4.5

---

## P0 - FIX IMMEDIATELY (Security/Crash)

### 1. Shell Injection Vulnerabilities

```bash
# Files to fix:
scripts/call-cursor.sh       # Lines 82, 85
scripts/call-gemini.sh       # Lines 78, 84
orchestrator/utils/git_operations.py  # Lines 70-78
orchestrator/validation/tdd.py        # Lines 180, 184, 194
orchestrator/testing/bdd_runner.py    # Lines 265, 277
orchestrator/testing/playwright_runner.py  # Lines 203, 227
```

**Fix**: Use `shlex.quote()` for all shell arguments. Replace `subprocess_shell` with `subprocess_exec`.

### 2. File Descriptor Exhaustion

```python
# File: orchestrator/utils/logging.py:265-272
# Problem: Opens 2 files per log call

# Fix: Use file handle pooling or buffered writer
class OrchestrationLogger:
    def __init__(self, ...):
        self._log_handle = open(self.log_file, "a", buffering=1)
        self._json_handle = open(self.json_log_file, "a", buffering=1)
```

### 3. Async/Await Crash

```python
# File: orchestrator/orchestrator.py:127-143
# Problem: Sync method calls asyncio.run()

# Fix: Make proper async entry point
async def run_async(self, ...):
    # actual async implementation

def run(self, ...):
    return asyncio.run(self.run_async(...))
```

### 4. Missing VERSION File

```bash
# Create the file:
echo "3.0.0" > VERSION
```

### 5. Path Traversal

```python
# File: scripts/init.sh:83 and orchestrator/project_manager.py

# Fix: Validate project name
def validate_project_name(name: str) -> bool:
    if '..' in name or name.startswith('/') or name.startswith('~'):
        raise ValueError(f"Invalid project name: {name}")
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValueError(f"Project name must be alphanumeric: {name}")
    return True
```

---

## P1 - FIX THIS WEEK (Correctness)

### 6. Thread Safety in State Manager

```python
# File: orchestrator/utils/state.py:266-270

# Fix: Add lock to property
@property
def state(self) -> Dict[str, Any]:
    with self._lock:
        if self._state is None:
            self._state = self._load_state()
        return self._state.copy()  # Return copy
```

### 7. Infinite Loop in Task Selection

```python
# File: orchestrator/langgraph/routers/task.py:130-185

# Fix: Add deadlock detection
def verify_task_router(state: WorkflowState) -> str:
    available = get_available_tasks(state)
    if not available:
        remaining = [t for t in state.get("tasks", [])
                     if t["id"] not in state.get("completed_task_ids", [])]
        if remaining:
            # All remaining tasks are blocked - escalate
            return "human_escalation"
    # ... rest of router
```

### 8. Agent Retry Logic

```python
# File: orchestrator/recovery/handlers.py:271-311

# Fix: Actually perform retry
async def handle_agent_failure(self, error, context) -> RecoveryResult:
    if not context.details.get("used_backup", False):
        # Actually try backup CLI
        backup_result = await self._try_backup_cli(context)
        if backup_result.success:
            return RecoveryResult(action=RecoveryAction.CONTINUE, result=backup_result)
    # Then escalate
    return await self._escalate(error, context)
```

### 9. Circular Dependency Detection

```python
# File: orchestrator/langgraph/nodes/task_breakdown.py

# Add cycle detection
def detect_circular_dependencies(tasks: list[Task]) -> list[str]:
    """Detect circular dependencies using DFS."""
    graph = {t["id"]: t.get("dependencies", []) for t in tasks}
    visited = set()
    rec_stack = set()
    cycles = []

    def dfs(node, path):
        visited.add(node)
        rec_stack.add(node)
        for dep in graph.get(node, []):
            if dep not in visited:
                dfs(dep, path + [dep])
            elif dep in rec_stack:
                cycles.append(path + [dep])
        rec_stack.remove(node)

    for task_id in graph:
        if task_id not in visited:
            dfs(task_id, [task_id])
    return cycles
```

### 10. Subprocess Cleanup

```python
# File: orchestrator/project_manager.py:235-240

# Fix: Kill process on timeout
try:
    result = subprocess.run(cmd, timeout=timeout, ...)
except subprocess.TimeoutExpired as e:
    # Process is still running - kill it
    if hasattr(e, 'process'):
        e.process.kill()
        e.process.wait()
    raise
```

---

## P2 - FIX NEXT SPRINT (Quality)

### 11. Rate Limiter Thread Safety

```python
# File: orchestrator/sdk/rate_limiter.py:276-280

# Fix: Don't release lock during sleep
async def acquire(self, ...):
    async with self._lock:
        while True:
            allowed, reason = await self._check_limits(estimated_tokens)
            if allowed:
                return RateLimitContext(self)
            # Sleep WITHOUT releasing lock, use shorter intervals
            await asyncio.sleep(0.01)  # Yield but keep lock
```

### 12. Symlink Protection

```python
# File: orchestrator/utils/boundaries.py

def validate_orchestrator_write(project_dir: Path, target_path: Path) -> bool:
    project_dir = Path(project_dir).resolve()
    target_path = Path(target_path).resolve()

    # Check if target escapes via symlink
    try:
        # Ensure target is truly within project
        target_path.relative_to(project_dir)
    except ValueError:
        return False

    # Check no symlink in path escapes
    for parent in target_path.parents:
        if parent == project_dir:
            break
        if parent.is_symlink():
            real_parent = parent.resolve()
            try:
                real_parent.relative_to(project_dir)
            except ValueError:
                return False  # Symlink escapes

    # Rest of validation...
```

### 13. Atomic File Writes

```python
# File: orchestrator/utils/action_log.py

def _save_index(self) -> None:
    """Save index to file atomically."""
    import tempfile

    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(
        dir=self.index_file.parent,
        prefix='.index_',
        suffix='.tmp'
    )
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(self._index, f, indent=2)
        # Atomic rename
        os.replace(temp_path, self.index_file)
    except:
        os.unlink(temp_path)
        raise
```

### 14. Conflict Resolution Handler

```python
# File: orchestrator/review/cycle.py:305-314

# Fix: Handle CONFLICT decision
if decision == ReviewDecision.APPROVED:
    # ...existing code...
elif decision == ReviewDecision.CONFLICT:
    # Immediate escalation for unresolved conflicts
    logger.warning(f"Unresolved reviewer conflict for task {task.id}")
    return ReviewCycleResult(
        task_id=task.id,
        working_agent_id=working_agent_id,
        final_status="escalated",
        iterations=iterations,
        escalation_reason="Unresolved reviewer conflict",
    )
```

### 15. Secrets Redaction Enhancement

```python
# File: orchestrator/utils/logging.py

# Add more patterns
ADDITIONAL_PATTERNS = [
    (r'ghp_[a-zA-Z0-9]{36}', '***GITHUB_TOKEN***'),
    (r'ghu_[a-zA-Z0-9]{36}', '***GITHUB_TOKEN***'),
    (r'ANTHROPIC_API_KEY=[^\s]+', 'ANTHROPIC_API_KEY=***REDACTED***'),
    (r'AWS_SECRET_ACCESS_KEY=[^\s]+', 'AWS_SECRET_ACCESS_KEY=***REDACTED***'),
]

# Also redact keys, not just values
def _redact_dict(self, data: dict) -> dict:
    result = {}
    for key, value in data.items():
        redacted_key = self._redactor.redact(str(key))
        if isinstance(value, str):
            result[redacted_key] = self._redactor.redact(value)
        # ...
```

---

## Quick Reference Commands

```bash
# Run security audit
grep -rn "subprocess.*shell=True" orchestrator/
grep -rn "create_subprocess_shell" orchestrator/
grep -rn "format(" scripts/*.sh

# Find all file opens
grep -rn "open(" orchestrator/utils/

# Find missing tests
for f in orchestrator/**/*.py; do
    base=$(basename "$f" .py)
    if [[ ! -f "tests/test_${base}.py" ]]; then
        echo "MISSING: $f"
    fi
done

# Check for race conditions
grep -rn "self\._" orchestrator/ | grep -v "self\._lock"
```

---

## Verification Checklist

After fixes, verify:

- [ ] `./scripts/init.sh init "test; ls"` fails with validation error
- [ ] 1000 log messages don't cause "too many open files"
- [ ] `python -c "import asyncio; asyncio.run(orchestrator.run())"` works
- [ ] `pip install .` succeeds (VERSION file exists)
- [ ] Circular dependencies detected and reported
- [ ] Subprocess timeouts actually kill processes
- [ ] Symlinks in .workflow/ don't escape to src/

---

*Generated from pre-mortem analysis*
