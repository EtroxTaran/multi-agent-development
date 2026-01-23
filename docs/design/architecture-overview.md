# Part II: Architecture (For Technical Leaders)

## 4. System Architecture

### 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CONDUCTOR SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      ORCHESTRATION LAYER                             │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │  LangGraph   │  │   State      │  │  Recovery    │               │   │
│  │  │  Workflow    │  │   Manager    │  │  Handler     │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        AGENT LAYER                                   │   │
│  │                                                                      │   │
│  │   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │   │
│  │   │ Claude  │ │ Cursor  │ │ Gemini  │ │ Claude  │ │ Cursor  │      │   │
│  │   │ Planner │ │ SecRev  │ │ CodeRev │ │ Worker  │ │ BugFix  │      │   │
│  │   │  (A01)  │ │  (A07)  │ │  (A08)  │ │  (A04)  │ │  (A05)  │      │   │
│  │   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘      │   │
│  │                                                                      │   │
│  │   + A02 Architect, A03 Test Writer, A06 Refactorer,                 │   │
│  │     A09 Docs, A10 Integration, A11 DevOps, A12 UI Designer          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                       PROJECT LAYER                                  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  projects/<name>/                                             │   │   │
│  │  │  ├── PRODUCT.md           <- Feature specification           │   │   │
│  │  │  ├── CLAUDE.md            <- Worker context                   │   │   │
│  │  │  ├── .workflow/           <- Orchestrator state              │   │   │
│  │  │  ├── src/                 <- Application code (workers)      │   │   │
│  │  │  └── tests/               <- Test files (workers)            │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Separation of Concerns** | Each agent has narrow, focused responsibilities |
| **Defense in Depth** | Multiple validation layers (TDD, 4-eyes, verification) |
| **Fail-Safe** | Errors are caught, logged, and escalated—never silently ignored |
| **Idempotent Operations** | Resumable from any checkpoint |
| **Human-in-the-Loop** | Escalation for ambiguous decisions |

### 4.3 Critical Design Decisions

#### Decision 1: Sequential Writes, Parallel Reads
- Only one agent writes to application code at a time
- Multiple agents can read in parallel
- **Rationale**: Prevents merge conflicts and race conditions

#### Decision 2: File Boundary Enforcement
- Orchestrator can ONLY write to `.workflow/` and `.project-config.json`
- Workers can ONLY write to `src/` and `tests/`
- **Rationale**: Clear separation of concerns, prevents accidents

#### Decision 3: Tests are Source of Truth
- Tests represent the specification
- If tests fail, fix the code, NOT the tests
- Test modifications require human approval
- **Rationale**: Maintains specification integrity

#### Decision 4: 4-Eyes Mandatory
- Every task verified by 2 different CLI/model combinations
- Security issues: Cursor's assessment preferred (0.8 weight)
- Architecture issues: Gemini's assessment preferred (0.7 weight)
- **Rationale**: Different AI systems catch different issues

### 4.4 Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Workflow Engine | LangGraph | Graph-based workflow with checkpointing |
| State Persistence | SQLite | Checkpoint storage via SqliteSaver |
| Agent CLIs | Claude, Cursor, Gemini | AI coding assistants |
| Language | Python 3.12+ | Orchestration logic |
| Parallelism | Git Worktrees | Isolated parallel execution |

---

## 5. The 5-Phase Workflow

### 5.1 Phase Overview

```
PRODUCT.md ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► DONE
               (Plan)    (Validate)  (Implement)  (Verify)   (Complete)
                 │           │            │           │           │
                 ▼           ▼            ▼           ▼           ▼
             plan.json    feedback    code+tests   reviews    summary
                        (parallel)   (TDD loop)  (parallel)
```

| Phase | Name | Agent(s) | Output | Gate |
|-------|------|----------|--------|------|
| 1 | Planning | Claude (A01) | `plan.json`, task list | Plan created |
| 2 | Validation | Cursor + Gemini (parallel) | Feedback, approval | Score >= 6.0 |
| 3 | Implementation | Claude (A04) + workers | Code, tests | Tests pass |
| 4 | Verification | Cursor + Gemini (parallel) | Approval/rejection | Score >= 7.0 |
| 5 | Completion | Orchestrator | Final report | Summary generated |

### 5.2 Phase 1: Planning

**Purpose**: Break the feature into discrete, implementable tasks

**Input**:
- `PRODUCT.md` (feature specification)
- `Documents/` folder (architecture docs)

**Output**:
- `.workflow/phases/planning/plan.json`
- Task list with dependencies

**Process**:
1. Read and analyze PRODUCT.md
2. Identify discrete tasks (max 2-4 hours each)
3. Determine dependencies between tasks
4. Assign appropriate agents to each task
5. Set acceptance criteria

### 5.3 Phase 2: Validation

**Purpose**: Verify the plan before implementation begins

**Agents**: Cursor (security) + Gemini (architecture) in parallel

**Validation Criteria**:

| Reviewer | Focus Areas |
|----------|-------------|
| Cursor | Security risks, test coverage gaps, vulnerabilities |
| Gemini | Architecture soundness, scalability, design patterns |

**Gate Requirements**:
- Both reviewers must score >= 6.0
- No blocking issues identified
- If rejected: return to Phase 1 with feedback

### 5.4 Phase 3: Implementation

**Purpose**: Build the feature using TDD

**Process**:
```
For each task:
    1. Write failing tests (A03 Test Writer)
    2. Implement code to pass tests (A04 Implementer)
    3. Run tests and verify
    4. If tests fail: A05 Bug Fixer attempts repair
    5. After 3 failures: escalate to human
```

**TDD Enforcement**:
- Tests must fail initially (proves they test something)
- Tests must cover acceptance criteria
- Implementation must be minimal to pass tests
- Workers cannot modify test assertions

### 5.5 Phase 4: Verification

**Purpose**: Final review before completion

**Agents**: Cursor (security) + Gemini (code quality) in parallel

**Verification Criteria**:

| Reviewer | Focus Areas |
|----------|-------------|
| Cursor | OWASP Top 10, injection risks, authentication flaws |
| Gemini | Code quality, patterns, maintainability, performance |

**Gate Requirements**:
- Both reviewers must score >= 7.0 (higher than Phase 2)
- No blocking security issues
- No critical architecture issues

### 5.6 Phase 5: Completion

**Purpose**: Generate summary and finalize

**Output**:
- `.workflow/phases/completion/summary.json`
- Metrics (tokens used, files changed, test coverage)
- Ready-for-merge status

---

## 6. Agent Registry (12 Specialists)

### 6.1 Agent Overview

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
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 CLI Specialization Matrix

Each CLI has different strengths:

| Capability | Claude | Cursor | Gemini |
|------------|--------|--------|--------|
| Context Window | 200K | 128K | 1M |
| Code Generation | 5/5 | 4/5 | 4/5 |
| Debugging | 4/5 | 5/5 | 3/5 |
| Security Review | 4/5 | 5/5 | 3/5 |
| Architecture | 4/5 | 3/5 | 5/5 |
| Refactoring | 4/5 | 3/5 | 5/5 |

### 6.3 Task-to-CLI Routing

Tasks are automatically routed to the best CLI:

```python
TASK_ROUTING = {
    "planning": ("claude", "gemini"),
    "architecture": ("gemini", "claude"),
    "test_writing": ("claude", "cursor"),
    "implementation": ("claude", "cursor"),
    "debugging": ("cursor", "claude"),
    "refactoring": ("gemini", "claude"),
    "security_review": ("cursor", "claude"),
    "code_review": ("gemini", "cursor"),
    "documentation": ("claude", "gemini"),
}
```

### 6.4 Agent Context Files

Each agent has context files in `agents/<ID>-<name>/`:

```
agents/
├── A01-planner/
│   ├── CLAUDE.md           # Claude-specific instructions
│   ├── GEMINI.md           # Gemini backup instructions
│   └── TOOLS.json          # Allowed tools
├── A04-implementer/
│   ├── CLAUDE.md           # Primary instructions
│   └── TOOLS.json          # Read, Write, Edit, Bash(test commands)
├── A07-security-reviewer/
│   ├── CURSOR-RULES.md     # Cursor-specific rules
│   └── owasp_checklist.md  # OWASP Top 10 checklist
└── ... (all 12 agents)
```

---

## 7. Quality Assurance System

### 7.1 The 4-Eyes Protocol

**Principle**: Every task must be verified by at least 2 different CLI/agent combinations before completion.

```
Task Complete ───► Verifier 1 (CLI-A) ───► Verifier 2 (CLI-B)
                         │                       │
                   ┌─────┴─────┐           ┌─────┴─────┐
                   │           │           │           │
                APPROVE     REJECT      APPROVE     REJECT
                   │           │           │           │
                   └─────┬─────┘           └─────┬─────┘
                         │                       │
                  If V1 approved          If both approved
                  but V2 rejected:          ──────► DONE
                         │
                         ▼
                  CONFLICT RESOLUTION
                  (weighted scoring)
```

### 7.2 Verification Matrix

| Task Type | Primary Verifier | Secondary Verifier |
|-----------|------------------|-------------------|
| Tests | A08 (Gemini) | A07 (Cursor) |
| Implementation | A07 (Cursor) | A08 (Gemini) |
| Refactoring | A08 (Gemini) | A07 (Cursor) |
| Bug Fix | A10 (Claude) | A08 (Gemini) |
| Security Fix | A08 (Gemini) | External Scan |

### 7.3 Conflict Resolution

When reviewers disagree, weighted scoring determines the outcome:

```python
CONFLICT_WEIGHTS = {
    "security": {"A07": 0.8, "A08": 0.2},    # Security reviewer wins
    "architecture": {"A08": 0.7, "A07": 0.3}, # Code reviewer wins
    "general": {"A07": 0.5, "A08": 0.5},      # Equal, escalate if tie
}
```

### 7.4 Scoring System

| Score | Meaning |
|-------|---------|
| 9-10 | Excellent, ready to merge |
| 7-8 | Good, minor improvements suggested |
| 5-6 | Acceptable, some changes recommended |
| 3-4 | Needs work, significant issues |
| 1-2 | Reject, fundamental problems |

---

## 8. Universal Agent Loop

### 8.1 Overview

The Universal Agent Loop enables iterative TDD execution across all agents (Claude, Cursor, Gemini) through a unified interface.

### 8.2 Supported Agents and Models

| Agent | Available Models | Completion Signal | Key Capabilities |
|-------|------------------|-------------------|------------------|
| **Claude** | sonnet, opus, haiku | `<promise>DONE</promise>` | Session continuity, plan mode, budget control |
| **Cursor** | codex-5.2, composer | `{"status": "done"}` | Model selection, JSON output |
| **Gemini** | gemini-2.0-flash, gemini-2.0-pro | `DONE`, `COMPLETE` | Model selection |

### 8.3 Verification Strategies

The loop supports pluggable verification after each iteration:

| Strategy | Description | Frameworks |
|----------|-------------|------------|
| `tests` | Run test suite | pytest, jest, vitest, bun test, cargo test, go test |
| `lint` | Run linters | ruff, eslint, clippy, golangci-lint |
| `security` | Run security scans | bandit, npm audit, cargo audit, semgrep |
| `composite` | Combine multiple | Configurable combination |
| `none` | No verification | For tasks without tests |

### 8.4 Usage Example

```python
from orchestrator.langgraph.integrations.unified_loop import (
    UnifiedLoopRunner,
    UnifiedLoopConfig,
    LoopContext,
)

# Configure the loop
config = UnifiedLoopConfig(
    agent_type="cursor",
    model="codex-5.2",
    verification="tests",
    max_iterations=10,
    budget_per_iteration=0.50,
)

# Create runner
runner = UnifiedLoopRunner(project_dir, config)

# Run with context
context = LoopContext(
    task_id="T1",
    title="Implement user authentication",
    test_files=["tests/test_auth.py"],
)

result = await runner.run("T1", context=context)
print(f"Success: {result.success}, Iterations: {result.iterations}")
```

### 8.5 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `USE_UNIFIED_LOOP` | Enable unified loop | `false` |
| `LOOP_AGENT` | Override agent selection | - |
| `LOOP_MODEL` | Override model selection | - |

---
