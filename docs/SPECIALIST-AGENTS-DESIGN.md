# Specialist Agents Architecture Design

**Version**: 3.0
**Date**: 2026-01-21
**Status**: Implemented

---

## Executive Summary

This document proposes a complete overhaul of the multi-agent system from "generalist agents doing phases" to **specialized micro-agents** with narrow contexts, clear responsibilities, and strict verification protocols. Like a human development team where each person has specific skills (tester, implementer, security reviewer, etc.), each agent becomes a specialist.

### Key Principles

1. **Narrow Context = Better Quality**: Smaller, focused context files lead to more reliable outputs
2. **4-Eyes Principle**: Every task verified by at least 2 different CLI/model combinations
3. **Kanban Board**: Markdown-based task board that all agents can read/write
4. **CLI Specialization**: Match CLI strengths to task types
5. **More Agents > Fewer Agents**: 10+ specialist agents better than 3 generalists

---

## Part 1: Specialist Agent Definitions

### Agent Registry

| ID | Agent Name | Primary CLI | Backup CLI | Specialty |
|----|------------|-------------|------------|-----------|
| `A01` | **Planner** | Claude | Gemini | High-level planning, task breakdown |
| `A02` | **Architect** | Gemini | Claude | System design, large-context analysis |
| `A03` | **Test Writer** | Claude | Cursor | TDD test creation (tests FIRST) |
| `A04` | **Implementer** | Claude | Cursor | Code implementation |
| `A05` | **Bug Fixer** | Cursor | Claude | Debugging, error resolution |
| `A06` | **Refactorer** | Gemini | Claude | Large-scale refactoring |
| `A07` | **Security Reviewer** | Cursor | Claude | OWASP, vulnerability scanning |
| `A08` | **Code Reviewer** | Gemini | Cursor | Architecture, patterns, quality |
| `A09` | **Documentation** | Claude | Gemini | Docs, comments, README |
| `A10` | **Integration Tester** | Claude | Cursor | E2E tests, integration tests |
| `A11` | **DevOps** | Cursor | Claude | CI/CD, deployment, Docker |
| `A12` | **UX/UI Designer** | Claude | Gemini | Component design, accessibility |

---

### Agent Context Files Structure

Each agent has its own context directory:

```
agents/
├── A01-planner/
│   ├── CLAUDE.md           # Claude-specific instructions
│   ├── GEMINI.md           # Gemini-specific instructions
│   ├── .cursor/rules       # Cursor-specific rules
│   ├── PROMPT.md           # Default system prompt
│   ├── TOOLS.json          # Allowed tools list
│   └── EXAMPLES.md         # Few-shot examples
├── A02-architect/
│   ├── CLAUDE.md
│   ├── GEMINI.md
│   └── ...
└── ...
```

---

## Part 2: Detailed Agent Specifications

### A01 - Planner Agent

**Purpose**: Break down features into discrete, implementable tasks

**Context Size**: ~3,000 tokens (minimal)

**Input**:
- PRODUCT.md (feature specification)
- Documents/ folder (architecture docs)

**Output**:
- `tasks.json` - Structured task list
- Updates to `.board/backlog.md`

**CLAUDE.md for Planner**:
```markdown
# Planner Agent Context

You are a PLANNER ONLY. You do NOT write code.

## Your Role
- Read PRODUCT.md and understand the feature
- Break it into discrete tasks (max 2-4 hours each)
- Identify dependencies between tasks
- Assign task types (test, implement, refactor, etc.)

## Output Format
Always output JSON:
{
  "tasks": [
    {
      "id": "T001",
      "title": "Write unit tests for auth service",
      "type": "test",
      "agent": "A03",
      "dependencies": [],
      "acceptance_criteria": ["..."],
      "estimated_complexity": "medium"
    }
  ]
}

## Rules
- NEVER suggest implementation details
- NEVER assign more than 5 files per task
- Each task must have clear acceptance criteria
- Tests come before implementation (TDD)
```

---

### A03 - Test Writer Agent

**Purpose**: Write failing tests FIRST (TDD)

**Context Size**: ~4,000 tokens

**Input**:
- Single task from backlog
- Existing test patterns (if any)
- API contracts/interfaces

**Output**:
- Test files only
- Test report (which tests should fail initially)

**CLAUDE.md for Test Writer**:
```markdown
# Test Writer Agent Context

You are a TEST WRITER ONLY. You write FAILING tests first.

## Your Role
- Read the task acceptance criteria
- Write comprehensive test cases
- Tests MUST fail initially (no implementation yet)
- Cover edge cases and error conditions

## Test Patterns
- Use Arrange-Act-Assert pattern
- One assertion per test when possible
- Test names describe behavior: test_should_return_error_when_invalid

## Output
1. Test files in tests/ directory
2. JSON report:
{
  "agent": "A03",
  "task_id": "T001",
  "tests_written": ["tests/test_auth.py"],
  "expected_failures": 5,
  "coverage_targets": ["src/auth.py"]
}

## Rules
- NEVER write implementation code
- NEVER modify src/ files
- NEVER skip edge cases
- Include both positive and negative tests
```

---

### A04 - Implementer Agent

**Purpose**: Write code to make tests pass

**Context Size**: ~5,000 tokens

**Input**:
- Task from backlog
- Existing failing tests
- Related source files

**Output**:
- Implementation code
- All tests passing

**CLAUDE.md for Implementer**:
```markdown
# Implementer Agent Context

You are an IMPLEMENTER. You make failing tests pass.

## Your Role
- Read the failing tests
- Implement minimal code to pass tests
- Follow existing code patterns
- Keep implementations simple

## Process
1. Read all failing tests first
2. Understand what behavior is expected
3. Write implementation
4. Run tests after each change
5. Stop when all tests pass

## Output
{
  "agent": "A04",
  "task_id": "T001",
  "files_modified": ["src/auth.py"],
  "tests_passing": true,
  "test_results": {"passed": 5, "failed": 0}
}

## Rules
- NEVER modify test files
- NEVER add features beyond what tests require
- NEVER refactor unrelated code
- Keep changes minimal
```

---

### A05 - Bug Fixer Agent

**Purpose**: Debug and fix failing tests/errors

**Context Size**: ~4,000 tokens

**Primary CLI**: **Cursor** (best at debugging)

**Input**:
- Error logs/stack traces
- Failing test output
- Related source files

**Output**:
- Bug fix with explanation
- Updated tests if bug was in test

**.cursor/rules for Bug Fixer**:
```
# Bug Fixer Agent Rules

You are a BUG FIXER. You debug and fix issues.

## Your Role
- Analyze error messages and stack traces
- Identify root cause (not symptoms)
- Apply minimal fix
- Verify fix doesn't break other tests

## Debug Process
1. Read the error message carefully
2. Trace the execution path
3. Identify the exact failing point
4. Understand WHY it fails
5. Apply targeted fix
6. Run full test suite

## Output JSON
{
  "agent": "A05",
  "task_id": "T001",
  "bug_description": "Off-by-one error in loop",
  "root_cause": "Array index started at 1 instead of 0",
  "fix_applied": "Changed loop start from 1 to 0",
  "files_modified": ["src/utils.py:42"],
  "regression_check": "All 15 tests pass"
}

## Rules
- NEVER add features while fixing
- NEVER refactor during bug fix
- Document the root cause
- Verify no regressions
```

---

### A06 - Refactorer Agent

**Purpose**: Large-scale code improvements

**Context Size**: ~10,000 tokens (large context needed)

**Primary CLI**: **Gemini** (1M token context)

**Input**:
- Codebase sections to refactor
- Target patterns/architecture
- Existing test coverage

**Output**:
- Refactored code
- All tests still passing

**GEMINI.md for Refactorer**:
```markdown
# Refactorer Agent Context

You are a REFACTORER. You improve code structure without changing behavior.

## Your Role
- Analyze large code sections
- Identify patterns and anti-patterns
- Apply consistent improvements
- Maintain all existing behavior (tests must pass)

## Refactoring Types
- Extract functions/methods
- Consolidate duplicate code
- Improve naming consistency
- Apply design patterns
- Reduce complexity

## Process
1. Load full context of files to refactor
2. Run tests to establish baseline (must pass)
3. Apply incremental refactoring
4. Run tests after each change
5. Stop if any test fails

## Output
{
  "agent": "A06",
  "task_id": "T010",
  "changes": [
    {"type": "extract_function", "from": "auth.py:50-80", "to": "auth.py:validate_token()"},
    {"type": "rename", "from": "x", "to": "user_count"}
  ],
  "tests_passing": true,
  "complexity_before": 45,
  "complexity_after": 28
}

## Rules
- NEVER change behavior
- NEVER add features
- Tests MUST pass at every step
- Document every change
```

---

### A07 - Security Reviewer Agent

**Purpose**: Find and flag security vulnerabilities

**Context Size**: ~3,000 tokens

**Primary CLI**: **Cursor** (security-focused)

**Input**:
- Code to review
- OWASP checklist
- Security requirements

**Output**:
- Security report
- Severity ratings
- Remediation suggestions

**.cursor/rules for Security Reviewer**:
```
# Security Reviewer Agent Rules

You are a SECURITY REVIEWER. You find vulnerabilities.

## OWASP Top 10 Checklist
1. Injection (SQL, Command, XSS)
2. Broken Authentication
3. Sensitive Data Exposure
4. XML External Entities
5. Broken Access Control
6. Security Misconfiguration
7. Cross-Site Scripting (XSS)
8. Insecure Deserialization
9. Using Components with Known Vulnerabilities
10. Insufficient Logging & Monitoring

## Review Process
1. Scan for hardcoded secrets
2. Check input validation
3. Verify authentication flows
4. Check authorization checks
5. Review data encryption
6. Check error handling (no info leak)
7. Verify parameterized queries

## Output JSON
{
  "agent": "A07",
  "task_id": "T015",
  "findings": [
    {
      "severity": "CRITICAL",
      "type": "SQL_INJECTION",
      "file": "src/db.py:45",
      "description": "String concatenation in SQL query",
      "remediation": "Use parameterized query"
    }
  ],
  "approved": false,
  "score": 3.5
}

## Rules
- NEVER approve code with CRITICAL issues
- NEVER fix code yourself (flag only)
- Rate severity: CRITICAL, HIGH, MEDIUM, LOW, INFO
- Always explain WHY it's a vulnerability
```

---

### A08 - Code Reviewer Agent

**Purpose**: Review code quality, patterns, architecture

**Context Size**: ~8,000 tokens

**Primary CLI**: **Gemini** (architecture understanding)

**Input**:
- Code to review
- Project conventions
- Architecture docs

**Output**:
- Review report
- Approval decision
- Improvement suggestions

**GEMINI.md for Code Reviewer**:
```markdown
# Code Reviewer Agent Context

You are a CODE REVIEWER. You evaluate code quality and architecture.

## Review Criteria
1. **Correctness**: Does code do what it should?
2. **Clarity**: Is code readable and understandable?
3. **Consistency**: Does it follow project patterns?
4. **Completeness**: Are edge cases handled?
5. **Performance**: Any obvious inefficiencies?
6. **Testability**: Can code be easily tested?

## Review Process
1. Understand the task requirements
2. Read the implementation
3. Check against acceptance criteria
4. Verify test coverage
5. Look for code smells
6. Provide actionable feedback

## Output
{
  "agent": "A08",
  "task_id": "T001",
  "approved": true,
  "score": 8.5,
  "comments": [
    {"file": "src/auth.py:50", "type": "suggestion", "comment": "Consider extracting magic number 86400 to SECONDS_PER_DAY constant"}
  ],
  "blocking_issues": [],
  "summary": "Clean implementation, minor suggestions only"
}

## Scoring
- 9-10: Excellent, ready to merge
- 7-8: Good, minor improvements suggested
- 5-6: Acceptable, some changes recommended
- 3-4: Needs work, significant issues
- 1-2: Reject, fundamental problems

## Rules
- Be specific in feedback (file:line)
- Distinguish blocking vs. non-blocking issues
- Don't nitpick style (that's linter's job)
- Focus on logic and architecture
```

---

## Part 3: Kanban Board System

### Board Structure

```
.board/
├── backlog.md          # Tasks ready to be picked up
├── in-progress.md      # Currently being worked on
├── review.md           # Awaiting verification
├── done.md             # Completed and verified
├── blocked.md          # Blocked tasks with reason
└── archive/            # Historical completed tasks
    └── 2026-01-21.md
```

### Task Card Format

Each task in the board files follows this format:

```markdown
## [T001] Write unit tests for auth service

| Field | Value |
|-------|-------|
| **ID** | T001 |
| **Type** | test |
| **Agent** | A03 (Test Writer) |
| **Verifiers** | A07 (Security), A08 (Code Review) |
| **Priority** | high |
| **Complexity** | medium |
| **Dependencies** | None |
| **Blocked By** | - |

### Acceptance Criteria
- [ ] Tests cover login flow
- [ ] Tests cover logout flow
- [ ] Tests cover token refresh
- [ ] Edge cases: expired token, invalid token

### Files
- Create: `tests/test_auth.py`
- Read: `src/auth.py` (for interface)

### History
| Timestamp | Agent | Action |
|-----------|-------|--------|
| 2026-01-21 10:00 | A01 | Created task |
| 2026-01-21 10:15 | A03 | Started implementation |

---
```

### Board Transitions

```
┌─────────────────────────────────────────────────────────────────┐
│                         BOARD FLOW                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  BACKLOG ──────► IN-PROGRESS ──────► REVIEW ──────► DONE       │
│     │                 │                 │              │        │
│     │                 │                 │              ▼        │
│     │                 │                 │          ARCHIVE      │
│     │                 │                 │                       │
│     │                 ▼                 ▼                       │
│     └────────────► BLOCKED ◄────────────                       │
│                       │                                         │
│                       └──────► ESCALATION (Human)              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Board Reader/Writer Protocol

All agents must follow this protocol:

```python
# Read board state
def read_board_state():
    """Every agent reads this before starting work."""
    return {
        "backlog": parse_tasks(".board/backlog.md"),
        "in_progress": parse_tasks(".board/in-progress.md"),
        "review": parse_tasks(".board/review.md"),
        "blocked": parse_tasks(".board/blocked.md"),
    }

# Claim a task
def claim_task(agent_id: str, task_id: str):
    """Move task from backlog to in-progress."""
    # 1. Remove from backlog.md
    # 2. Add to in-progress.md with agent assignment
    # 3. Add history entry

# Submit for review
def submit_for_review(agent_id: str, task_id: str, output: dict):
    """Move task from in-progress to review."""
    # 1. Remove from in-progress.md
    # 2. Add to review.md with output summary
    # 3. Assign verifiers (4-eyes: 2 different agents)

# Complete review
def complete_review(agent_id: str, task_id: str, approved: bool):
    """Move task from review to done or back to in-progress."""
    if approved:
        # Move to done.md
    else:
        # Move back to in-progress.md with feedback
```

---

## Part 4: CLI Tool Mapping

### Model Strengths Matrix

| Capability | Claude | Cursor | Gemini | Best For |
|------------|--------|--------|--------|----------|
| **Context Window** | 200K | 128K | 1M | Large files: Gemini |
| **Code Generation** | ★★★★★ | ★★★★☆ | ★★★★☆ | Claude |
| **Debugging** | ★★★★☆ | ★★★★★ | ★★★☆☆ | Cursor |
| **Security Review** | ★★★★☆ | ★★★★★ | ★★★☆☆ | Cursor |
| **Architecture** | ★★★★☆ | ★★★☆☆ | ★★★★★ | Gemini |
| **Refactoring** | ★★★★☆ | ★★★☆☆ | ★★★★★ | Gemini |
| **Test Writing** | ★★★★★ | ★★★★☆ | ★★★★☆ | Claude |
| **Documentation** | ★★★★★ | ★★★☆☆ | ★★★★☆ | Claude |
| **Speed** | ★★★★☆ | ★★★★★ | ★★★☆☆ | Cursor |
| **Cost** | $$$ | $$ | $ | Gemini |

### Task-to-CLI Routing

```python
TASK_ROUTING = {
    # Task Type -> (Primary CLI, Backup CLI)
    "planning": ("claude", "gemini"),
    "architecture": ("gemini", "claude"),
    "test_writing": ("claude", "cursor"),
    "implementation": ("claude", "cursor"),
    "debugging": ("cursor", "claude"),
    "refactoring": ("gemini", "claude"),
    "security_review": ("cursor", "claude"),
    "code_review": ("gemini", "cursor"),
    "documentation": ("claude", "gemini"),
    "integration_test": ("claude", "cursor"),
    "devops": ("cursor", "claude"),
    "ui_design": ("claude", "gemini"),
}
```

### CLI Invocation Patterns

```bash
# Claude - Best for: Planning, Testing, Implementation, Docs
claude -p "<prompt>" \
    --output-format json \
    --allowedTools "Read,Write,Edit,Bash(npm*),Bash(pytest*)" \
    --max-turns 20 \
    --append-system-prompt-file agents/A04-implementer/CLAUDE.md

# Cursor - Best for: Debugging, Security, Speed
cursor-agent --print \
    --output-format json \
    --force \
    "<prompt with .cursor/rules loaded>"

# Gemini - Best for: Architecture, Refactoring, Large Context
gemini --yolo \
    --model gemini-2.5-pro \
    "<prompt>"
```

---

## Part 5: 4-Eyes Verification Protocol

### Principle

**Every task must be verified by at least 2 different CLI/agent combinations before completion.**

### Verification Matrix

| Task Type | Primary Verifier | Secondary Verifier | Notes |
|-----------|------------------|-------------------|-------|
| Tests | A08 (Gemini) | A07 (Cursor) | Architecture + Security |
| Implementation | A07 (Cursor) | A08 (Gemini) | Security + Quality |
| Refactoring | A08 (Gemini) | A07 (Cursor) | Quality + Security |
| Bug Fix | A10 (Claude) | A08 (Gemini) | Integration + Quality |
| Security Fix | A08 (Gemini) | External Scan | Double security check |

### Verification Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    4-EYES VERIFICATION                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Task Complete ───► Verifier 1 (CLI-A) ───► Verifier 2 (CLI-B) │
│        │                   │                       │            │
│        │            ┌──────┴──────┐         ┌──────┴──────┐     │
│        │            │             │         │             │     │
│        │         APPROVE       REJECT    APPROVE       REJECT   │
│        │            │             │         │             │     │
│        │            │             │         │             │     │
│        │            └──────┬──────┘         └──────┬──────┘     │
│        │                   │                       │            │
│        │                   ▼                       ▼            │
│        │           If V1 approved           If both approved    │
│        │           but V2 rejected:          ──────► DONE       │
│        │                   │                                    │
│        │                   ▼                                    │
│        │            CONFLICT RESOLUTION                         │
│        │            (weighted scoring)                          │
│        │                   │                                    │
│        │         ┌─────────┴─────────┐                         │
│        │         │                   │                         │
│        │     Security wins       Escalate to                   │
│        │     (weight: 0.8)       Human                         │
│        │                                                        │
└─────────────────────────────────────────────────────────────────┘
```

### Verification Output Format

```json
{
  "task_id": "T001",
  "verifications": [
    {
      "verifier": "A07",
      "cli": "cursor",
      "approved": true,
      "score": 8.5,
      "concerns": [],
      "blocking_issues": [],
      "timestamp": "2026-01-21T10:30:00Z"
    },
    {
      "verifier": "A08",
      "cli": "gemini",
      "approved": true,
      "score": 9.0,
      "concerns": [
        {"type": "suggestion", "comment": "Consider adding docstring"}
      ],
      "blocking_issues": [],
      "timestamp": "2026-01-21T10:35:00Z"
    }
  ],
  "final_decision": "approved",
  "combined_score": 8.75,
  "ready_for_done": true
}
```

### Conflict Resolution Rules

```python
CONFLICT_WEIGHTS = {
    "A07_security": 0.8,    # Security reviewer weight on security issues
    "A08_architecture": 0.7, # Code reviewer weight on architecture issues
    "A07_general": 0.5,     # Equal weight on general issues
    "A08_general": 0.5,
}

def resolve_conflict(v1_result, v2_result, issue_type):
    """Resolve conflicting verification results."""

    if issue_type == "security":
        # Security reviewer (A07/Cursor) wins
        return v1_result if v1_result["verifier"] == "A07" else v2_result

    if issue_type == "architecture":
        # Code reviewer (A08/Gemini) wins
        return v1_result if v1_result["verifier"] == "A08" else v2_result

    # For general issues: escalate to human
    return {"decision": "escalate", "reason": "Conflicting reviews, human decision needed"}
```

---

## Part 6: Cognitive Orchestration (Self-Healing)

### Architecture Upgrade (v4.0)

The system now includes a **Cognitive Fixer Loop** that handles errors intelligently instead of blindly retrying.

```
ERROR OCCURS
    │
    ▼
┌──────────────┐
│  A05 FIXER   │
│ (Triage Node)│
└──────┬───────┘
       │
       ├──► Simple? (Syntax, Import) ──► Regex Fix ──► Apply
       │
       └──► Complex? (Logic, API) ──► LLM Diagnosis
                                           │
                                           ▼
                                     Knowledge Gap?
                                     (e.g., API misuse)
                                      /          \
                                    YES           NO
                                     │             │
                            ┌────────▼───────┐     │
                            │ RESEARCH PHASE │     │
                            │ (Read Docs)    │     │
                            └────────┬───────┘     │
                                     │             │
                                     ▼             ▼
                                Create Plan ──► Apply Fix
```

### Components

| Component | Role | Logic |
|-----------|------|-------|
| **Triage** | Router | Regex-based categorization. Decides: Fix, Escalate, or Skip. |
| **Diagnoser** | Analyst | **Fast Path**: Regex patterns. **Slow Path**: LLM analysis of stack trace + code. |
| **Researcher** | Scholar | Spawns if `RootCause` is "API_MISUSE" or "MISSING_DOCS". Reads docs/files to learn correct usage. |
| **Patcher** | Surgeon | Generates minimal diffs based on the plan. |

### Dynamic Adaptation

This architecture allows the system to **learn at runtime**. If a library implementation fails because the agent "hallucinated" an API, the Research Phase forces it to check the actual code/docs, correcting its internal context before retrying.

---

## Part 7: Workflow Integration

### Updated LangGraph Workflow

```
                    ┌─────────────────┐
                    │   ORCHESTRATOR  │
                    │   (Claude)      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   A01: PLANNER  │
                    │   (Claude)      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ TASK BREAKDOWN  │
                    │ → .board/backlog│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ TASK LOOP START │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ A03:TEST │   │ A04:IMPL │   │ A05:FIX  │
        │ (Claude) │   │ (Claude) │   │ (Cursor) │
        └────┬─────┘   └────┬─────┘   └────┬─────┘
             │              │              │
             └──────────────┼──────────────┘
                            │
                    ┌───────▼───────┐
                    │ SUBMIT REVIEW │
                    │ (4-Eyes)      │
                    └───────┬───────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
        ┌──────────┐               ┌──────────┐
        │ A07:SEC  │               │ A08:CODE │
        │ (Cursor) │               │ (Gemini) │
        └────┬─────┘               └────┬─────┘
             │                          │
             └────────────┬─────────────┘
                          │
                    ┌─────▼─────┐
                    │  FAN-IN   │
                    │ (Resolve) │
                    └─────┬─────┘
                          │
                ┌─────────┼─────────┐
                │         │         │
            APPROVED   REJECTED   CONFLICT
                │         │         │
                ▼         ▼         ▼
             DONE    RETRY    ESCALATE
                          │
                    ┌─────▼─────┐
                    │LOOP BACK  │
                    │(next task)│
                    └───────────┘
```

### Orchestrator Role: Tech Lead

The **Orchestrator** (Claude) acts as the **Tech Lead** - autonomous for day-to-day operations, escalating only when real decisions are needed.

#### Identity

| Aspect | Description |
|--------|-------------|
| **Role** | Tech Lead / Team Coordinator |
| **Autonomy** | High - runs task by task without intervention |
| **Escalates** | Only for blockers, spec conflicts, or decisions |
| **Never Does** | Write application code directly |

#### Autonomous Operations (No Human Needed)

The orchestrator handles these independently:

- Pick next task from backlog based on priority/dependencies
- Assign task to appropriate specialist agent
- Run 4-eyes verification with A07 + A08
- Move tasks through the board (backlog → in-progress → review → done)
- Handle routine retries (up to 3 attempts per task)
- Apply conflict resolution weights
- Progress through entire feature if all goes smoothly

#### Escalate to Human When

| Situation | Trigger | Example |
|-----------|---------|---------|
| **Blocker** | External dependency missing | "Need OAuth credentials" |
| **Spec Unclear** | PRODUCT.md ambiguous | "Timeout not specified" |
| **Conflict** | Verifiers disagree, weights don't resolve | "Security vs Architecture" |
| **Max Retries** | 3 attempts failed | "Test still failing after 3 tries" |
| **Out of Scope** | Change requires spec modification | "Needs database schema change" |
| **Test vs Spec Conflict** | Test doesn't match PRODUCT.md | "Test expects X, spec says Y" |

---

### Test Failure Protocol

**CRITICAL RULE: Tests are the source of truth. Fix the code, not the tests.**

Tests represent the product vision from PRODUCT.md. When tests fail:

| Situation | Action | Escalate? |
|-----------|--------|-----------|
| Test fails, implementation has bug | A05 (Bug Fixer) fixes the code | NO |
| Test fails, need different approach | A04 (Implementer) tries new approach | NO |
| Test fails 3x, still can't pass | Investigate root cause, then escalate | YES |
| Test contradicts PRODUCT.md | Escalate: "Test says X, spec says Y" | YES |
| Test is technically impossible | Escalate with proof of why | YES |

#### Test Failure Handling Flow

```
Test Fails
    │
    ▼
┌─────────────────────────────┐
│ A05 Bug Fixer investigates  │
│ - Read error message        │
│ - Trace root cause          │
│ - Attempt fix               │
└─────────────┬───────────────┘
              │
         Fix works?
        /         \
      YES          NO
       │            │
       ▼            ▼
    DONE      Attempt 2
               (A04 tries
              new approach)
                   │
              Fix works?
             /         \
           YES          NO
            │            │
            ▼            ▼
         DONE       Attempt 3
                    (A05 deep
                     debug)
                        │
                   Fix works?
                  /         \
                YES          NO
                 │            │
                 ▼            ▼
              DONE     ESCALATE
                      (with full
                       context)
```

#### When Tests Can Be Modified

Tests should **only** be modified when:

1. Test has a bug (typo, wrong assertion)
2. Test doesn't match PRODUCT.md (spec conflict)
3. Human explicitly approves test change

In all these cases: **ESCALATE FIRST**, don't auto-modify tests.

---

### Investigation Protocol

**RULE: Always investigate before escalating. Never waste human time.**

Before any escalation, the orchestrator must:

```
INVESTIGATION CHECKLIST:
□ What exactly failed? (error message, stack trace)
□ Why did it fail? (root cause analysis)
□ What approaches were tried? (attempts 1, 2, 3)
□ Why can't we fix it autonomously? (the blocker)
□ What are the options? (A/B/C with pros/cons)
□ Is there a recommended option? (if clear choice exists)
```

#### Example: Good Escalation (After Investigation)

```
ESCALATION: Cannot satisfy test_session_expires_after_30min

CONTEXT:
Task T003 requires implementing session expiration.
Test expects sessions to expire after exactly 30 minutes.

ROOT CAUSE ANALYSIS:
- Checked PRODUCT.md: Says "sessions should timeout for security"
  but NO specific duration mentioned
- Checked Documents/security.md: Says "implement session timeout"
  but NO duration specified
- The test (written by A03) assumed 30 minutes

ATTEMPTS MADE:
1. Implemented 30-minute timeout → Test passes, but is this correct?
2. Checked similar features in codebase → No precedent found
3. Searched Documents/ for timeout policies → None found

THE PROBLEM:
Test has specific expectation (30 min) but spec is ambiguous.
We cannot determine the correct value autonomously.

OPTIONS:
A) Accept 30 minutes as default
   + Test passes immediately
   - May not match actual product requirement

B) Use 24 hours (more "convenient" per spec language)
   + Aligns with "user convenience" mentioned in spec
   - Test would need updating (requires your approval)

C) Use configurable timeout with 30-min default
   + Flexible for future changes
   - More complex than needed if requirement is simple

D) You specify the correct duration
   + Guaranteed correct
   - Requires your input

RECOMMENDATION: Option D - this is a product decision that
should be documented in PRODUCT.md for future reference.

What would you like to do?
```

#### Example: NOT an Escalation (Handled Autonomously)

```
[INTERNAL - Human never sees this]

Test: test_login_returns_token
Error: AssertionError: expected token, got None

A05 Bug Fixer Analysis:
- Error: login() returns None instead of token
- Root cause: Missing return statement on line 45
- Fix: Added "return token" after token generation

Result: All 8 tests now pass
Action: Continue to next task
```

---

### Escalation Format

When escalation is needed, use this format:

```markdown
## ESCALATION: [Brief Title]

### Context
- What task/feature we're working on
- What we were trying to do
- Current state of the board

### Root Cause Analysis
- What exactly went wrong
- Why it went wrong
- What we investigated

### Attempts Made
1. First approach - result
2. Second approach - result
3. Third approach - result

### The Blocker
Clear statement of why we cannot proceed autonomously.

### Options
**A) [First Option]**
- Description
- Pros: ...
- Cons: ...

**B) [Second Option]**
- Description
- Pros: ...
- Cons: ...

**C) [Investigate Further / Other]**
- What additional investigation would involve
- Expected outcome

### Recommendation
[If there's a clear best choice, state it. Otherwise: "Need your input."]

---
What would you like to do?
```

---

### Summary: Orchestrator Principles

| Principle | Behavior |
|-----------|----------|
| **Autonomous by Default** | Run tasks without asking |
| **Tests = Spec** | Never rewrite tests to make them pass |
| **Investigate First** | Find root cause before escalating |
| **Escalate with Context** | Full analysis + options + recommendation |
| **Don't Waste Time** | Only escalate real decisions |
| **Tech Lead Role** | Coordinate team, handle routine issues |

---

### Implementation Plan

```python
# New nodes for specialist agents
SPECIALIST_NODES = [
    "planner",           # A01 - creates tasks
    "test_writer",       # A03 - writes failing tests
    "implementer",       # A04 - makes tests pass
    "bug_fixer",         # A05 - fixes failures
    "refactorer",        # A06 - code improvements
    "security_reviewer", # A07 - security check (4-eyes #1)
    "code_reviewer",     # A08 - quality check (4-eyes #2)
    "integration_tester",# A10 - E2E tests
]

# Board management nodes
BOARD_NODES = [
    "read_board",        # Load current board state
    "select_task",       # Pick next task from backlog
    "assign_agent",      # Route to specialist
    "submit_review",     # Move to review queue
    "process_review",    # 4-eyes verification
    "resolve_conflict",  # Handle disagreements
    "complete_task",     # Move to done
]
```

---

## Part 8: Directory Structure

### New Project Structure

```
conductor/
├── agents/                          # Agent definitions
│   ├── A01-planner/
│   │   ├── CLAUDE.md
│   │   ├── GEMINI.md
│   │   ├── .cursor/rules
│   │   ├── PROMPT.md
│   │   └── TOOLS.json
│   ├── A02-architect/
│   ├── A03-test-writer/
│   ├── A04-implementer/
│   ├── A05-bug-fixer/
│   ├── A06-refactorer/
│   ├── A07-security-reviewer/
│   ├── A08-code-reviewer/
│   ├── A09-documentation/
│   ├── A10-integration-tester/
│   ├── A11-devops/
│   └── A12-ui-designer/
│
├── orchestrator/
│   ├── agents/                      # CLI wrappers
│   │   ├── base.py
│   │   ├── claude_agent.py
│   │   ├── cursor_agent.py
│   │   └── gemini_agent.py
│   │
│   ├── specialists/                 # Specialist agent runners
│   │   ├── planner.py
│   │   ├── test_writer.py
│   │   ├── implementer.py
│   │   └── ...
│   │
│   ├── board/                       # Kanban board management
│   │   ├── reader.py
│   │   ├── writer.py
│   │   ├── transitions.py
│   │   └── parser.py
│   │
│   ├── verification/                # 4-eyes protocol
│   │   ├── dispatcher.py
│   │   ├── collector.py
│   │   ├── resolver.py
│   │   └── weights.py
│   │
│   └── langgraph/                   # Workflow graph
│       ├── nodes/
│       │   ├── specialist_nodes.py  # NEW: Specialist dispatch
│       │   ├── board_nodes.py       # NEW: Board management
│       │   └── verification_nodes.py # NEW: 4-eyes nodes
│       └── workflow.py
│
└── projects/
    └── <project-name>/
        ├── .board/                  # Project's Kanban board
        │   ├── backlog.md
        │   ├── in-progress.md
        │   ├── review.md
        │   ├── done.md
        │   ├── blocked.md
        │   └── archive/
        │
        ├── .workflow/               # Workflow state
        │   └── state.json
        │
        ├── Documents/               # Product docs
        ├── PRODUCT.md               # Feature spec
        ├── CLAUDE.md                # Project-specific Claude context
        ├── GEMINI.md                # Project-specific Gemini context
        └── .cursor/rules            # Project-specific Cursor rules
```

---

## Part 9: Migration Path

### Phase 1: Create Agent Definitions (Week 1)
- [ ] Create `agents/` directory structure
- [ ] Write CLAUDE.md, GEMINI.md, .cursor/rules for each agent
- [ ] Define TOOLS.json (allowed tools per agent)
- [ ] Add few-shot examples in EXAMPLES.md

### Phase 2: Implement Board System (Week 2)
- [ ] Create board parser (markdown ↔ structured data)
- [ ] Implement board transitions
- [ ] Add board state reading to all agents
- [ ] Create board management CLI commands

### Phase 3: Specialist Runners (Week 3)
- [ ] Create specialist runner classes
- [ ] Implement CLI routing logic
- [ ] Add context loading from agent directories
- [ ] Test each specialist in isolation

### Phase 4: 4-Eyes Verification (Week 4)
- [ ] Implement verification dispatcher
- [ ] Create result collector/merger
- [ ] Implement conflict resolution
- [ ] Add weight-based scoring

### Phase 5: LangGraph Integration (Week 5)
- [ ] Create new specialist nodes
- [ ] Create board management nodes
- [ ] Create verification nodes
- [ ] Update workflow graph
- [ ] Test full flow

### Phase 6: Testing & Refinement (Week 6)
- [ ] End-to-end testing
- [ ] Tune conflict weights
- [ ] Optimize context sizes
- [ ] Documentation

---

## Part 10: Configuration

### Environment Variables

```bash
# CLI Paths
CLAUDE_CLI_PATH=/usr/local/bin/claude
CURSOR_CLI_PATH=/usr/local/bin/cursor-agent
GEMINI_CLI_PATH=/usr/local/bin/gemini

# Model Selection
CLAUDE_MODEL=claude-opus-4.5
CURSOR_MODEL=gpt-4.5-turbo
GEMINI_MODEL=gemini-2.5-pro

# Verification Thresholds
VERIFICATION_SCORE_THRESHOLD=7.0
SECURITY_SCORE_THRESHOLD=8.0

# 4-Eyes Weights
SECURITY_WEIGHT=0.8
ARCHITECTURE_WEIGHT=0.7

# Board Settings
MAX_WIP_TASKS=3
MAX_TASK_RETRIES=3
```

### Project Config (.project-config.json)

```json
{
  "project_name": "my-api",
  "created_at": "2026-01-21T10:00:00Z",
  "agents": {
    "enabled": ["A01", "A03", "A04", "A05", "A07", "A08"],
    "disabled": ["A12"]
  },
  "verification": {
    "require_4_eyes": true,
    "security_threshold": 8.0,
    "quality_threshold": 7.0
  },
  "board": {
    "max_wip": 3,
    "auto_archive_days": 7
  }
}
```

---

## Part 11: Success Metrics

### Quality Metrics
- **First-pass success rate**: % of tasks passing 4-eyes on first submission
- **Security issue detection rate**: % of vulnerabilities caught before merge
- **Bug escape rate**: Bugs found in production vs. caught by agents

### Efficiency Metrics
- **Task cycle time**: Time from backlog to done
- **Verification turnaround**: Time for 4-eyes verification
- **Conflict rate**: % of tasks requiring human escalation

### Cost Metrics
- **Tokens per task**: Average token usage per task type
- **CLI distribution**: Usage distribution across Claude/Cursor/Gemini
- **Cost per feature**: Total API cost per completed feature

---

## Appendix A: Agent Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT QUICK REFERENCE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  A01 PLANNER      │ Claude  │ Breaks features into tasks       │
│  A02 ARCHITECT    │ Gemini  │ System design, large context     │
│  A03 TEST WRITER  │ Claude  │ Writes failing tests (TDD)       │
│  A04 IMPLEMENTER  │ Claude  │ Makes tests pass                 │
│  A05 BUG FIXER    │ Cursor  │ Debugs and fixes issues          │
│  A06 REFACTORER   │ Gemini  │ Large-scale improvements         │
│  A07 SECURITY REV │ Cursor  │ OWASP, vulnerabilities           │
│  A08 CODE REVIEW  │ Gemini  │ Quality, architecture            │
│  A09 DOCS         │ Claude  │ Documentation, comments          │
│  A10 INTEGRATION  │ Claude  │ E2E tests                        │
│  A11 DEVOPS       │ Cursor  │ CI/CD, deployment                │
│  A12 UI/UX        │ Claude  │ Component design                 │
│                                                                 │
│  4-EYES RULE: Every task verified by 2 different CLIs          │
│  BOARD: backlog → in-progress → review → done                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix B: Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-21 | 12 specialist agents | More specialization = narrower context = better quality |
| 2026-01-21 | Cursor for security | Best at finding vulnerabilities |
| 2026-01-21 | Gemini for refactoring | 1M context window needed |
| 2026-01-21 | Markdown board | Simple, version-controlled, human-readable |
| 2026-01-21 | 4-eyes mandatory | Dual verification catches more issues |
| 2026-01-21 | Orchestrator = Tech Lead | Autonomous operations, escalate only for real decisions |
| 2026-01-21 | Tests are source of truth | Never modify tests to make them pass; fix the code instead |
| 2026-01-21 | Investigate before escalate | Root cause + options required; don't waste human time |
| 2026-01-21 | 3 retries before escalate | Give agents fair chance to solve problems autonomously |

---

## Next Steps

1. **Review this design** with stakeholders
2. **Prioritize agents** (start with A01, A03, A04, A07, A08)
3. **Prototype board system** with markdown parser
4. **Test CLI routing** in isolation
5. **Build incrementally** following migration phases
