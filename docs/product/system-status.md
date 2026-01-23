# Meta-Architect System Status

**Last Updated**: 2026-01-23
**Version**: 3.2
**Test Coverage**: 1600+ tests passing

---

## System Overview

Meta-Architect is a production-grade multi-agent orchestration system that coordinates specialist AI agents (Claude, Cursor, Gemini) to implement features through a structured 5-phase workflow with TDD, 4-eyes review protocol, and comprehensive error recovery.

---

## Core Components

### 1. Task Management System

| Component | Location | Purpose |
|-----------|----------|---------|
| Task Breakdown | `orchestrator/langgraph/nodes/task_breakdown.py` | Parses PRODUCT.md into discrete tasks |
| Task Selection | `orchestrator/langgraph/nodes/select_task.py` | Selects next available task based on priority & dependencies |
| Task Implementation | `orchestrator/langgraph/nodes/implement_task.py` | Spawns worker Claude for implementation |
| Task Verification | `orchestrator/langgraph/nodes/verify_task.py` | Runs tests, verifies file creation |

**Task Flow**:
```
PRODUCT.md → task_breakdown → select_task → implement_task → verify_task → [loop until done]
```

### 2. Universal Agent Loop System

| Component | Location | Purpose |
|-----------|----------|---------|
| Agent Adapter | `orchestrator/agents/adapter.py` | Unified interface for all agents |
| Unified Loop | `orchestrator/langgraph/integrations/unified_loop.py` | Iterative TDD execution |
| Verification | `orchestrator/langgraph/integrations/verification.py` | Pluggable verification strategies |

**Supported Agents**:

| Agent | Models | Completion Signal | Capabilities |
|-------|--------|-------------------|--------------|
| Claude | sonnet, opus, haiku | `<promise>DONE</promise>` | Session, plan mode, budget |
| Cursor | codex-5.2, composer | `{"status": "done"}` | Model selection, JSON output |
| Gemini | gemini-2.0-flash, gemini-2.0-pro | `DONE`, `COMPLETE` | Model selection |

**Verification Strategies**:

| Strategy | Description | Frameworks |
|----------|-------------|------------|
| tests | Run test suite | pytest, jest, vitest, bun test, cargo test, go test |
| lint | Run linters | ruff, eslint, clippy, golangci-lint |
| security | Run security scans | bandit, npm audit, cargo audit, semgrep |
| composite | Combine multiple strategies | Configurable |

**Environment Variables**:
- `USE_UNIFIED_LOOP=true` - Enable unified loop
- `LOOP_AGENT=cursor` - Override agent selection
- `LOOP_MODEL=codex-5.2` - Override model selection

### 4. Agent Registry

| Agent | Role | Primary CLI | Reviewers |
|-------|------|-------------|-----------|
| A01 | Planner | Claude | A08, A02 |
| A02 | Architect | Gemini | A08, A01 |
| A03 | Test Writer | Claude | A08, A07 |
| A04 | Implementer | Claude | A07, A08 |
| A05 | Bug Fixer | Cursor | A10, A08 |
| A06 | Refactorer | Gemini | A08, A07 |
| A07 | Security Reviewer | Cursor | - |
| A08 | Code Reviewer | Gemini | - |
| A09 | Documentation | Claude | A08, A01 |
| A10 | Integration Tester | Claude | A07, A08 |
| A11 | DevOps | Cursor | A07, A08 |
| A12 | UI Designer | Claude | A08, A07 |

**File**: `orchestrator/registry/agents.py`

### 5. Review System (4-Eyes Protocol)

| Component | Location | Purpose |
|-----------|----------|---------|
| Review Cycle | `orchestrator/review/cycle.py` | Manages iterative review-optimize-review loop |
| Conflict Resolver | `orchestrator/review/resolver.py` | Resolves reviewer disagreements with weighted scoring |

**Review Weights**:
- Security issues: Cursor's assessment preferred (0.8 weight)
- Architecture issues: Gemini's assessment preferred (0.7 weight)

**Review Flow**:
```
Agent Work → Cursor Review || Gemini Review → Fan-In → Decision
    ↑                                                    ↓
    └──────────── Feedback Loop ←───────── Needs Changes
```

### 6. Error Handling & Recovery

| Error Type | Recovery Strategy |
|------------|-------------------|
| TRANSIENT | Exponential backoff with jitter (max 3 retries) |
| AGENT_FAILURE | Try backup CLI, then escalate |
| REVIEW_CONFLICT | Apply weights, escalate if unresolved |
| SPEC_MISMATCH | Always escalate (never auto-modify tests) |
| BLOCKING_SECURITY | Immediate halt and escalate |
| TIMEOUT | One retry with extended timeout |

**File**: `orchestrator/recovery/handlers.py`

### 7. Logging System

| Output | Location | Format |
|--------|----------|--------|
| Console | stdout | Colored, human-readable |
| Plain Text | `.workflow/coordination.log` | Timestamped |
| JSON Lines | `.workflow/coordination.jsonl` | Machine-parseable |

**Features**:
- Automatic secrets redaction (API keys, passwords, tokens)
- Thread-safe with locks
- Color-coded log levels (DEBUG, INFO, WARNING, ERROR, SUCCESS, PHASE, AGENT)

**File**: `orchestrator/utils/logging.py`

### 8. Escalation System

When errors can't be resolved automatically, escalations are written to:
```
.workflow/escalations/{task_id}_{timestamp}.json
```

**Escalation Contents**:
- Task ID and context
- Reason for escalation
- Attempts made
- Available options
- Recommended action
- Severity level (low, medium, high, critical)

### 9. Rate Limiting

| Service | RPM | TPM | Hourly Cost Limit |
|---------|-----|-----|-------------------|
| Claude | 60 | 100K | $10 |
| Gemini | 60 | 200K | $15 |

**File**: `orchestrator/sdk/rate_limiter.py`

**Features**:
- Token bucket algorithm
- Exponential backoff on throttle
- Cost tracking per day/hour
- Concurrent request support

### 10. UI System

| Mode | Description |
|------|-------------|
| Interactive | Rich-based terminal UI with progress bars, task tree, metrics |
| Plaintext | Simple timestamped output for CI/headless environments |

**Auto-detection**: Detects CI environment variables, NO_COLOR, TTY status

**File**: `orchestrator/ui/`

---

## Workflow Phases

| Phase | Name | Description |
|-------|------|-------------|
| 1 | Planning | Claude generates implementation plan from PRODUCT.md |
| 2 | Validation | Cursor + Gemini review plan in parallel |
| 3 | Implementation | Worker Claude implements tasks with TDD |
| 4 | Verification | Cursor + Gemini review code in parallel |
| 5 | Completion | Generate summary, cleanup |

---

## File Structure

```
.workflow/
├── coordination.log              # Plain text logs
├── coordination.jsonl            # JSON logs for analysis
├── escalations/                  # Escalation requests
│   └── {task_id}_{timestamp}.json
├── task_clarifications/          # Human clarification requests
│   └── {task_id}_request.json
├── issue_mapping.json            # Linear issue ID mapping
└── phases/
    ├── planning/
    │   └── plan.json
    ├── validation/
    │   ├── cursor_feedback.json
    │   └── gemini_feedback.json
    ├── task_breakdown/
    │   └── tasks.json
    ├── task_implementation/
    │   └── {task_id}_result.json
    ├── task_verification/
    │   └── {task_id}_verification.json
    ├── verification/
    │   ├── cursor_review.json
    │   └── gemini_review.json
    └── completion/
        └── summary.json
```

---

## Debugging Guide

### 1. Check Workflow Status
```bash
./scripts/init.sh status <project-name>
# or
python -m orchestrator --project <name> --status
```

### 2. View Log Files

**Human-readable logs**:
```bash
tail -f projects/<name>/.workflow/coordination.log
```

**Machine-parseable logs** (for analysis):
```bash
cat projects/<name>/.workflow/coordination.jsonl | jq
```

### 3. Check Escalations

When workflow pauses for human input:
```bash
cat projects/<name>/.workflow/escalations/*.json | jq
```

Each escalation file contains:
- `task_id`: Which task failed
- `reason`: Why it failed
- `context`: Full error context
- `attempts_made`: How many retries occurred
- `options`: Suggested actions
- `recommendation`: What the system recommends
- `severity`: How critical the issue is

### 4. Resume After Fixing Issues
```bash
python -m orchestrator --project <name> --resume
```

### 5. Reset and Retry
```bash
# Reset all phases
python -m orchestrator --project <name> --reset

# Reset specific phase
python -m orchestrator --project <name> --reset --phase 3
```

### 6. Rollback to Previous State
```bash
python -m orchestrator --project <name> --rollback 3
```

---

## Common Issues and Solutions

### Issue: "PRODUCT.md validation failed"
**Cause**: PRODUCT.md doesn't meet minimum requirements
**Solution**: Ensure PRODUCT.md has:
- Feature Name (5-100 chars)
- Summary (50-500 chars)
- Problem Statement (min 100 chars)
- At least 3 acceptance criteria with `- [ ]` items
- At least 2 Example Inputs/Outputs with code blocks
- No placeholders like `[TODO]`, `[TBD]`

### Issue: "Agent failed on both primary and backup CLI"
**Cause**: Both Claude and fallback CLI failed
**Solution**:
1. Check escalation file for detailed error
2. Verify CLI tools are working: `./scripts/init.sh check`
3. Check rate limits haven't been exceeded

### Issue: "Max iterations exceeded"
**Cause**: Task couldn't be completed in allowed retries
**Solution**:
1. Check escalation for specific failure reason
2. Review the feedback from reviewers
3. Consider breaking task into smaller subtasks

### Issue: "Review conflict unresolved"
**Cause**: Cursor and Gemini disagree and weights don't resolve
**Solution**:
1. Check escalation for both reviews
2. Make manual decision on which reviewer to follow
3. Resume workflow with decision

### Issue: "Tests failing after implementation"
**Cause**: Implementation doesn't pass TDD tests
**Solution**:
1. Check `.workflow/phases/task_verification/{task_id}_verification.json`
2. Review test output for specific failures
3. Worker will auto-retry up to 3 times

---

## Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| Agent Registry | 19 | Passing |
| Agent Adapters | 36 | Passing |
| Verification Strategies | 41 | Passing |
| Unified Loop | 46 | Passing |
| Review Cycle | 17 | Passing |
| Cleanup & Recovery | 16 | Passing |
| SDK Rate Limiter | 46 | Passing |
| UI System | 38 | Passing |
| LangGraph Workflow | 150+ | Passing |
| Orchestrator | 12 | Passing |
| Validators | 20+ | Passing |
| Git Worktree | 18 | Passing |
| Session Manager | 21 | Passing |
| Error Context | 32 | Passing |
| Budget Manager | 25 | Passing |
| Audit Trail | 22 | Passing |
| Claude Agent Enhanced | 30 | Passing |
| GSD Enhancements | 50+ | Passing |
| **Total** | **1600+** | **All Passing** |

Run tests:
```bash
.venv/bin/python -m pytest tests/ -v
```

---

## Commands Reference

### Initialize Project
```bash
./scripts/init.sh init <project-name>
```

### Run Workflow
```bash
# Nested project
./scripts/init.sh run <project-name>

# External project
./scripts/init.sh run --path /path/to/project

# With parallel workers
./scripts/init.sh run <project-name> --parallel 3
```

### Check Status
```bash
./scripts/init.sh status <project-name>
```

### Python CLI
```bash
python -m orchestrator --project <name> --start
python -m orchestrator --project <name> --resume
python -m orchestrator --project <name> --status
python -m orchestrator --project <name> --reset
python -m orchestrator --project <name> --rollback 3
python -m orchestrator --project-path /external/path --start
```

---

## Integration Points

### Linear.com (Optional)
Configure in `.project-config.json`:
```json
{
  "integrations": {
    "linear": {
      "enabled": true,
      "team_id": "TEAM123"
    }
  }
}
```

Tasks are synced to Linear issues for project tracking.

### Git Auto-Commit
Enable to automatically commit after each phase:
```python
Orchestrator(project_dir, auto_commit=True)
```

---

## Performance Notes

- **Parallel validation**: Cursor and Gemini run simultaneously in Phase 2 and Phase 4
- **Task-based execution**: Features broken into small tasks for incremental verification
- **Rate limiting**: Built-in to prevent API overuse
- **Checkpoint/Resume**: Workflow can be resumed from any interruption point

---

## Security Features

- **Secrets Redaction**: Automatic in all logs
- **File Boundary Enforcement**: Orchestrator cannot write to src/, tests/, etc.
- **Security-First Review**: Security issues take priority in conflict resolution
- **No Auto-Fix for Security**: Blocking security issues always escalate
