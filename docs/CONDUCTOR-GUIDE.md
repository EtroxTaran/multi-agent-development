# Conductor: Complete System Guide

**The Definitive Reference for the Multi-Agent Orchestration System**

---

| **Document Info** | |
|-------------------|---|
| Version | 4.0 |
| Last Updated | 2026-01-22 |
| Test Coverage | 1,250+ tests passing |
| Codebase | ~20,000 lines of Python |
| License | Proprietary |

---

## Table of Contents

### For Everyone
1. [Executive Summary](#1-executive-summary)
2. [What Problem Does This Solve?](#2-what-problem-does-this-solve)
3. [Key Capabilities](#3-key-capabilities)

### For Technical Leaders
4. [System Architecture](#4-system-architecture)
5. [The 5-Phase Workflow](#5-the-5-phase-workflow)
6. [Agent Registry (12 Specialists)](#6-agent-registry-12-specialists)
7. [Quality Assurance System](#7-quality-assurance-system)
8. [Universal Agent Loop](#8-universal-agent-loop)

### For Developers
9. [Quick Start Guide](#9-quick-start-guide)
10. [Project Structure](#10-project-structure)
11. [Configuration Reference](#11-configuration-reference)
12. [CLI Commands](#12-cli-commands)
13. [Extending the System](#13-extending-the-system)

### Reference
14. [Error Handling & Recovery](#14-error-handling--recovery)
15. [Security Model](#15-security-model)
16. [Troubleshooting](#16-troubleshooting)
17. [Glossary](#17-glossary)
18. [Appendix: File Reference](#18-appendix-file-reference)

---

# Part I: Overview

## 1. Executive Summary

### What is Conductor?

Conductor is a **production-grade multi-agent orchestration system** that coordinates three AI coding assistants—Claude, Cursor, and Gemini—to automatically implement software features from specification to working code.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   PRODUCT.md ──────► CONDUCTOR ──────► Working Code   │
│   (Your Spec)         (5 Phases)           (Tested & Reviewed)
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Value Proposition

| Benefit | Description |
|---------|-------------|
| **Automated Feature Implementation** | From specification to working code without human coding |
| **Built-in Quality Assurance** | 4-eyes review protocol ensures every change is verified by 2 different AI reviewers |
| **Test-Driven Development** | Tests written first, code written to pass tests—always |
| **Error Recovery** | Automatic retries, checkpointing, and intelligent escalation |
| **Full Auditability** | Complete logging, state tracking, and decision trails |

### By the Numbers

| Metric | Value |
|--------|-------|
| Specialist Agents | 12 |
| Workflow Phases | 5 |
| Test Suite | 1,250+ tests |
| Code Coverage | ~85% |
| Supported AI CLIs | 3 (Claude, Cursor, Gemini) |

### Target Audience

- **Product Teams**: Accelerate feature development with AI-assisted implementation
- **Engineering Leaders**: Maintain quality standards while increasing velocity
- **Solo Developers**: Get expert-level code review on every change

---

## 2. What Problem Does This Solve?

### The Challenge

Traditional AI coding assistants are powerful but have limitations:

| Problem | Impact |
|---------|--------|
| **Single-model bias** | One AI may miss issues another would catch |
| **No quality gates** | Code goes straight to repo without review |
| **Context fragmentation** | Long conversations lose important context |
| **No TDD enforcement** | Tests often written after (or not at all) |
| **Manual coordination** | Developer must orchestrate multiple tools |

### The Solution

Conductor addresses these by:

1. **Multi-Agent Coordination**: Three different AI systems check each other's work
2. **Structured Workflow**: 5-phase process with checkpoints and gates
3. **Enforced TDD**: Tests must exist and pass before code is accepted
4. **4-Eyes Protocol**: Every task verified by 2 different CLI/model combinations
5. **Automated Orchestration**: System handles coordination automatically

### Before vs. After

```
BEFORE (Manual):
  Developer → Write Code → Maybe Test → Maybe Review → Merge

AFTER (Conductor):
  Developer → Write Spec → [Automated: Plan → Validate → Implement TDD → Verify] → Merge
```

---

## 3. Key Capabilities

### 3.1 Automated Feature Implementation

Write a specification, get working code:

```markdown
# In PRODUCT.md:
## Feature Name
User Authentication Service

## Acceptance Criteria
- [ ] Users can register with email
- [ ] Login returns JWT tokens
- [ ] Tokens expire after 15 minutes
```

The system automatically:
1. Creates an implementation plan
2. Writes failing tests first
3. Implements code to pass tests
4. Verifies with security and code review
5. Produces documented, tested, reviewed code

### 3.2 Multi-Agent Verification

Every task is verified by multiple AI systems:

```
Task Complete ──► Cursor (Security Review) ──┐
                                             ├──► Decision
Task Complete ──► Gemini (Code Review) ──────┘
```

### 3.3 Test-Driven Development

TDD is enforced, not optional:

```
1. Write Tests (must fail initially)
2. Implement Code (minimal to pass tests)
3. Refactor (tests must stay green)
```

### 3.4 Checkpoint & Resume

Work is never lost:

```bash
# Resume from where you left off
python -m orchestrator --project my-app --resume
```

### 3.5 Parallel Execution

Independent tasks run simultaneously:

```bash
# Run 3 workers in parallel
./scripts/init.sh run my-app --parallel 3
```

---

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

# Part III: Developer Guide

## 9. Quick Start Guide

### 9.1 Prerequisites

- Python 3.12+
- Claude Code CLI (`claude`)
- Cursor CLI (`cursor-agent`) - optional
- Gemini CLI (`gemini`) - optional
- Git (for parallel workers)

### 9.2 Installation

```bash
# Clone the repository
git clone https://github.com/your-org/conductor.git
cd conductor

# Install dependencies
uv sync  # or: pip install -e .

# Verify installation
./scripts/init.sh check
```

### 9.3 Your First Project

```bash
# Step 1: Initialize a project
./scripts/init.sh init my-first-app

# Step 2: Add your specification
cat > projects/my-first-app/PRODUCT.md << 'EOF'
# Feature Name
Hello World API

## Summary
Create a simple REST API that returns "Hello, World!" greeting.

## Problem Statement
We need a basic API endpoint for testing and demonstration purposes.
The endpoint should accept an optional name parameter and return a
personalized greeting.

## Acceptance Criteria
- [ ] GET /hello returns {"message": "Hello, World!"}
- [ ] GET /hello?name=Alice returns {"message": "Hello, Alice!"}
- [ ] Invalid requests return 400 status code
- [ ] Response time under 100ms

## Example Inputs/Outputs

### Basic greeting
```json
GET /hello
Response: {"message": "Hello, World!"}
```

### Named greeting
```json
GET /hello?name=Alice
Response: {"message": "Hello, Alice!"}
```

## Technical Constraints
- Use Python with FastAPI
- Include OpenAPI documentation
- Add request validation

## Testing Strategy
- Unit tests for greeting logic
- Integration tests for API endpoints

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Tests passing
- [ ] API documentation generated
- [ ] Code reviewed
EOF

# Step 3: Run the workflow
./scripts/init.sh run my-first-app

# Step 4: Check status
./scripts/init.sh status my-first-app
```

---

## 10. Project Structure

### 10.1 Nested Architecture

Conductor uses a two-layer nested architecture:

```
conductor/                     # OUTER LAYER (Orchestrator)
├── CLAUDE.md                       # Orchestrator context (workflow rules)
├── orchestrator/                   # Python orchestration module
├── scripts/                        # Agent invocation scripts
├── shared-rules/                   # Rules synced to all agents
└── projects/                       # Project containers
    └── <project-name>/             # INNER LAYER (Worker Claude)
        ├── Documents/              # Product vision, architecture docs
        ├── CLAUDE.md               # Worker context (coding rules)
        ├── GEMINI.md               # Gemini context
        ├── .cursor/rules           # Cursor context
        ├── PRODUCT.md              # Feature specification
        ├── .workflow/              # Orchestrator-writable state
        ├── src/                    # Worker-only: Application code
        └── tests/                  # Worker-only: Tests
```

### 10.2 File Boundary Rules

| Path | Orchestrator | Worker |
|------|--------------|--------|
| `.workflow/**` | **Write** | Read |
| `.project-config.json` | **Write** | Read |
| `src/**` | Read-only | **Write** |
| `tests/**` | Read-only | **Write** |
| `CLAUDE.md` | Read-only | Read |
| `PRODUCT.md` | Read-only | Read |

### 10.3 Workflow State Structure

```
.workflow/
├── state.json                    # Current workflow state
├── checkpoints.db                # LangGraph checkpoints (SQLite)
├── coordination.log              # Plain text logs
├── coordination.jsonl            # JSON logs for analysis
├── escalations/                  # Escalation requests
│   └── {task_id}_{timestamp}.json
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

## 11. Configuration Reference

### 11.1 PRODUCT.md Structure

Required sections for your feature specification:

```markdown
# Feature Name
[5-100 characters]

## Summary
[50-500 characters describing what the feature does]

## Problem Statement
[Minimum 100 characters explaining why this feature is needed]

## Acceptance Criteria
- [ ] Criterion 1 (minimum 3 required)
- [ ] Criterion 2
- [ ] Criterion 3

## Example Inputs/Outputs
[Minimum 2 examples with code blocks]

### Example 1
```json
// Input and expected output
```

### Example 2
```json
// Another example
```

## Technical Constraints
[Performance, security, compatibility requirements]

## Testing Strategy
[How the feature should be tested]

## Definition of Done
- [ ] Item 1 (minimum 5 required)
- [ ] Item 2
- [ ] Item 3
- [ ] Item 4
- [ ] Item 5
```

**Important**: No placeholders like `[TODO]`, `[TBD]`, or `...` — these will fail validation!

### 11.2 Project Configuration

`.project-config.json`:

```json
{
  "project_name": "my-app",
  "created_at": "2026-01-22T10:00:00Z",
  "workflow": {
    "parallel_workers": 3,
    "review_gating": "conservative"
  },
  "integrations": {
    "linear": {
      "enabled": true,
      "team_id": "TEAM123"
    }
  },
  "verification": {
    "require_4_eyes": true,
    "security_threshold": 8.0,
    "quality_threshold": 7.0
  }
}
```

### 11.3 Environment Variables

```bash
# Workflow Control
export ORCHESTRATOR_USE_LANGGRAPH=true
export USE_RALPH_LOOP=auto          # auto | true | false
export USE_UNIFIED_LOOP=true        # Enable unified agent loop
export PARALLEL_WORKERS=3           # Number of parallel workers

# Agent Selection
export LOOP_AGENT=cursor            # Override agent
export LOOP_MODEL=codex-5.2         # Override model

# Model Selection
export CLAUDE_MODEL=claude-opus-4.5
export CURSOR_MODEL=gpt-4.5-turbo
export GEMINI_MODEL=gemini-2.0-pro
```

---

## 12. CLI Commands

### 12.1 Shell Script Commands

```bash
# Check prerequisites
./scripts/init.sh check

# Initialize new project (nested)
./scripts/init.sh init <project-name>

# List all projects
./scripts/init.sh list

# Run workflow (nested project)
./scripts/init.sh run <project-name>

# Run workflow (external project)
./scripts/init.sh run --path /path/to/project

# Run with parallel workers
./scripts/init.sh run <project-name> --parallel 3

# Check status
./scripts/init.sh status <project-name>
```

### 12.2 Python CLI Commands

```bash
# Project Management
python -m orchestrator --init-project <name>
python -m orchestrator --list-projects

# Workflow Control (Nested)
python -m orchestrator --project <name> --start
python -m orchestrator --project <name> --resume
python -m orchestrator --project <name> --status
python -m orchestrator --project <name> --health
python -m orchestrator --project <name> --reset
python -m orchestrator --project <name> --rollback 3

# Workflow Control (External)
python -m orchestrator --project-path /path/to/project --start
python -m orchestrator --project-path /path/to/project --status

# With LangGraph
python -m orchestrator --project <name> --use-langgraph --start
```

### 12.3 Slash Commands (in Claude Code)

| Command | Description |
|---------|-------------|
| `/orchestrate --project <name>` | Start or resume workflow |
| `/phase-status --project <name>` | Show workflow status |
| `/list-projects` | List all projects |
| `/validate --project <name>` | Run Phase 2 validation manually |
| `/verify --project <name>` | Run Phase 4 verification manually |
| `/resolve-conflict --project <name>` | Resolve agent disagreements |

---

## 13. Extending the System

### 13.1 Adding a New Agent

1. Create agent directory:
```bash
mkdir -p agents/A13-new-agent
```

2. Add context files:
```
agents/A13-new-agent/
├── CLAUDE.md       # Claude-specific instructions
├── GEMINI.md       # Gemini backup instructions
├── CURSOR-RULES.md # Cursor-specific rules
└── TOOLS.json      # Allowed tools
```

3. Register in agent registry:
```python
# orchestrator/registry/agents.py
AGENTS = {
    # ... existing agents ...
    "A13": AgentConfig(
        id="A13",
        name="New Agent",
        primary_cli="claude",
        backup_cli="gemini",
        role="Description of role",
        reviewers=["A07", "A08"],
    ),
}
```

### 13.2 Adding a New Verification Strategy

```python
# orchestrator/langgraph/integrations/verification.py
class CustomVerificationStrategy(VerificationStrategy):
    """Custom verification strategy."""

    async def verify(self, context: VerificationContext) -> VerificationResult:
        # Your verification logic here
        return VerificationResult(
            success=True,
            message="Verification passed",
            details={},
        )

# Register the strategy
STRATEGIES["custom"] = CustomVerificationStrategy
```

### 13.3 Adding a New Phase

1. Create node function:
```python
# orchestrator/langgraph/nodes/new_phase.py
def new_phase_node(state: WorkflowState) -> dict:
    """Execute new phase logic."""
    # Your logic here
    return {"phase_result": result}
```

2. Add to workflow graph:
```python
# orchestrator/langgraph/workflow.py
workflow.add_node("new_phase", new_phase_node)
workflow.add_edge("previous_phase", "new_phase")
workflow.add_edge("new_phase", "next_phase")
```

---

# Part IV: Reference

## 14. Error Handling & Recovery

### 14.1 Error Categories

| Error Type | Description | Recovery Strategy |
|------------|-------------|-------------------|
| TRANSIENT | Temporary failures (network, rate limit) | Exponential backoff, max 3 retries |
| AGENT_FAILURE | Agent produces invalid output | Try backup CLI, then escalate |
| REVIEW_CONFLICT | Reviewers disagree | Apply weights, escalate if unresolved |
| SPEC_MISMATCH | Test doesn't match PRODUCT.md | Always escalate (never auto-fix) |
| BLOCKING_SECURITY | Critical vulnerability found | Immediate halt and escalate |
| TIMEOUT | Operation takes too long | One retry with extended timeout |

### 14.2 Escalation System

When errors can't be resolved automatically, escalations are created:

```
.workflow/escalations/{task_id}_{timestamp}.json
```

**Escalation Content**:
```json
{
  "task_id": "T003",
  "timestamp": "2026-01-22T14:30:00Z",
  "reason": "Max iterations exceeded",
  "context": {
    "attempts_made": 3,
    "error_history": ["...", "...", "..."],
    "last_error": "Tests still failing after 3 attempts"
  },
  "options": [
    "Retry with different approach",
    "Modify acceptance criteria",
    "Mark as blocked"
  ],
  "recommendation": "Review test expectations vs PRODUCT.md",
  "severity": "medium"
}
```

### 14.3 Test Failure Protocol

**Critical Rule**: Tests are the source of truth. Fix the code, not the tests.

```
Test Fails
    │
    ▼
A05 Bug Fixer investigates
    │
Fix works?
   /    \
 YES     NO
  │       │
DONE   Attempt 2 (A04 new approach)
           │
      Fix works?
         /    \
       YES     NO
        │       │
      DONE   Attempt 3 (A05 deep debug)
                 │
            Fix works?
               /    \
             YES     NO
              │       │
            DONE   ESCALATE
```

### 14.4 Self-Healing & Time Travel Debugging

Conductor includes advanced "Cognitive Orchestration" capabilities for resilience and debugging.

#### Deep Semantic Diagnosis
When errors occur, the system doesn't just blindly retry. It enters a "Fixer" loop:
1. **Triage:** Is it a syntax error, test failure, or something deeper?
2. **Diagnosis:** 
   - **Regex:** Fast path for common issues (missing imports, typos).
   - **Deep Semantic (LLM):** If complex, Claude analyzes the stack trace and logic to find the root cause.
3. **Dynamic Adaptation:** If the diagnosis reveals a knowledge gap (e.g., "API Misuse"), the system dynamically inserts a **Research Phase** to read documentation and generate a correct usage guide before retrying.
4. **Fix Application:** Generates and applies a specific patch.

#### Time Travel Debugging
Interactive debugging for the entire workflow state.

```bash
python -m orchestrator --project my-app --debug
```

**Debugger Commands:**
- `list`: Show all checkpoints (Start, Pre-Implementation, Error states).
- `checkout <id>`: Rollback the entire project state (files + memory) to that point.
- `replay`: Resume execution from the restored state.
- `inspect <id>`: View details of a checkpoint.

---

## 15. Security Model

### 15.1 File Boundary Enforcement

The orchestrator is sandboxed to prevent accidental code changes:

```python
# orchestrator/utils/boundaries.py

def validate_orchestrator_write(project_dir: Path, target_path: Path) -> bool:
    """Check if orchestrator is allowed to write to path."""
    relative = target_path.relative_to(project_dir)

    # Allowed paths
    if relative.parts[0] == ".workflow":
        return True
    if str(relative) == ".project-config.json":
        return True

    return False  # Block all other writes
```

### 15.2 Secrets Redaction

All logs automatically redact sensitive information:

- API keys (matches `sk-`, `api_key`, etc.)
- Passwords (matches `password`, `secret`, etc.)
- Tokens (matches `token`, `jwt`, `bearer`, etc.)

### 15.3 Rate Limiting

| Service | RPM | TPM | Hourly Cost Limit |
|---------|-----|-----|-------------------|
| Claude | 60 | 100K | $10 |
| Gemini | 60 | 200K | $15 |

### 15.4 Security Review Focus

Cursor (A07 Security Reviewer) checks for:

| Category | Checks |
|----------|--------|
| Injection | SQL injection, command injection, XSS |
| Authentication | Broken auth, session management |
| Data Protection | Sensitive data exposure, encryption |
| Access Control | Authorization flaws, privilege escalation |
| Configuration | Security misconfigurations, defaults |

---

## 16. Troubleshooting

### 16.1 Common Issues

#### Issue: "PRODUCT.md validation failed"
**Cause**: PRODUCT.md doesn't meet minimum requirements

**Solution**: Ensure PRODUCT.md has:
- Feature Name (5-100 chars)
- Summary (50-500 chars)
- Problem Statement (min 100 chars)
- At least 3 acceptance criteria with `- [ ]` items
- At least 2 Example Inputs/Outputs with code blocks
- No placeholders like `[TODO]`, `[TBD]`

#### Issue: "OrchestratorBoundaryError"
**Cause**: Orchestrator tried to write outside allowed paths

**Solution**: The orchestrator can only write to `.workflow/` and `.project-config.json`. If code changes are needed, they must go through worker agents.

#### Issue: "WorktreeError: not a git repository"
**Cause**: Parallel workers require git

**Solution**: Initialize a git repository or run without `--parallel`:
```bash
cd projects/my-app && git init
```

#### Issue: "Agent failed on both primary and backup CLI"
**Cause**: Both Claude and fallback CLI failed

**Solution**:
1. Check escalation file for detailed error
2. Verify CLI tools are working: `./scripts/init.sh check`
3. Check rate limits haven't been exceeded

#### Issue: "Max iterations exceeded"
**Cause**: Task couldn't be completed in allowed retries

**Solution**:
1. Check escalation for specific failure reason
2. Review the feedback from reviewers
3. Consider breaking task into smaller subtasks

### 16.2 Debugging Commands

```bash
# View human-readable logs
tail -f projects/<name>/.workflow/coordination.log

# View machine-parseable logs
cat projects/<name>/.workflow/coordination.jsonl | jq

# Check escalations
cat projects/<name>/.workflow/escalations/*.json | jq

# Resume after fixing issues
python -m orchestrator --project <name> --resume

# Reset and retry
python -m orchestrator --project <name> --reset
python -m orchestrator --project <name> --start
```

---

## 17. Glossary

| Term | Definition |
|------|------------|
| **4-Eyes Protocol** | Verification by 2 different AI systems before task completion |
| **Agent** | A specialist AI role (e.g., A04 Implementer, A07 Security Reviewer) |
| **CLI** | Command-line interface for an AI system (Claude, Cursor, Gemini) |
| **Escalation** | When the system cannot proceed and needs human input |
| **Gate** | A checkpoint that must pass before workflow proceeds |
| **LangGraph** | The graph-based workflow engine used for orchestration |
| **Nested Architecture** | Two-layer design with orchestrator (outer) and project (inner) |
| **Orchestrator** | The coordinating system that manages agents and workflow |
| **Phase** | One of the 5 stages in the workflow (Plan, Validate, Implement, Verify, Complete) |
| **PRODUCT.md** | The feature specification file that defines what to build |
| **Ralph Wiggum Loop** | Iterative TDD execution pattern with fresh context each iteration |
| **TDD** | Test-Driven Development: write tests first, then implementation |
| **Universal Agent Loop** | Unified interface for iterative execution across all agent types |
| **Worker** | An agent that writes application code (as opposed to orchestrator) |
| **Worktree** | Git feature used for isolated parallel execution |

---

## 18. Appendix: File Reference

### 18.1 Complete Directory Structure

```
conductor/
├── orchestrator/                    # Core orchestration module
│   ├── orchestrator.py              # Main Orchestrator class
│   ├── project_manager.py           # Project lifecycle
│   │
│   ├── agents/                      # CLI wrappers
│   │   ├── base.py                  # BaseAgent interface
│   │   ├── adapter.py               # Universal agent adapter
│   │   ├── claude_agent.py          # Claude CLI wrapper
│   │   ├── cursor_agent.py          # Cursor CLI wrapper
│   │   ├── gemini_agent.py          # Gemini CLI wrapper
│   │   ├── session_manager.py       # Session continuity
│   │   ├── error_context.py         # Error context preservation
│   │   └── budget.py                # Budget management
│   │
│   ├── langgraph/                   # LangGraph workflow
│   │   ├── workflow.py              # Graph definition
│   │   ├── state.py                 # State schema
│   │   ├── nodes/                   # Graph nodes
│   │   │   ├── planning.py
│   │   │   ├── validation.py
│   │   │   ├── task_breakdown.py
│   │   │   ├── select_task.py
│   │   │   ├── implement_task.py
│   │   │   ├── verify_task.py
│   │   │   └── completion.py
│   │   ├── routers/                 # Conditional edges
│   │   │   ├── phase.py
│   │   │   └── task.py
│   │   └── integrations/
│   │       ├── linear.py            # Linear.com integration
│   │       ├── ralph_loop.py        # TDD iteration loop
│   │       ├── unified_loop.py      # Universal agent loop
│   │       └── verification.py      # Verification strategies
│   │
│   ├── review/                      # Review system
│   │   ├── cycle.py                 # Review-optimize-review
│   │   └── resolver.py              # Conflict resolution
│   │
│   ├── recovery/                    # Error recovery
│   │   └── handlers.py
│   │
│   ├── validation/                  # Validators
│   │   ├── product_validator.py
│   │   └── tdd.py
│   │
│   ├── registry/                    # Agent registry
│   │   └── agents.py
│   │
│   ├── audit/                       # Audit trail
│   │   └── trail.py
│   │
│   ├── sdk/                         # SDK utilities
│   │   └── rate_limiter.py
│   │
│   ├── ui/                          # Terminal UI
│   │   ├── components.py
│   │   └── display.py
│   │
│   └── utils/                       # Utilities
│       ├── logging.py               # Logging with redaction
│       ├── state.py                 # State management
│       ├── boundaries.py            # File boundary enforcement
│       └── worktree.py              # Git worktree management
│
├── agents/                          # Agent context files
│   ├── A01-planner/
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
├── schemas/                         # JSON schemas
│   ├── plan-schema.json
│   ├── tasks-schema.json
│   ├── feedback-schema.json
│   └── project-config-schema.json
│
├── scripts/                         # Helper scripts
│   ├── init.sh                      # Main entry point
│   ├── call-cursor.sh               # Cursor CLI wrapper
│   ├── call-gemini.sh               # Gemini CLI wrapper
│   └── sync-rules.py                # Sync shared rules
│
├── shared-rules/                    # Rules for all agents
│   ├── core-rules.md
│   ├── coding-standards.md
│   ├── guardrails.md
│   ├── cli-reference.md
│   ├── lessons-learned.md
│   └── agent-overrides/
│       ├── claude.md
│       ├── cursor.md
│       └── gemini.md
│
├── docs/                            # Documentation
│   ├── CONDUCTOR-GUIDE.md      # This file
│   ├── quick-start.md
│   ├── SYSTEM-STATUS.md
│   ├── SPECIALIST-AGENTS-DESIGN.md
│   └── COMPREHENSIVE-SYSTEM-ANALYSIS.md
│
├── tests/                           # Test suite (1,250+ tests)
│   └── ...
│
├── projects/                        # Project containers
│   └── <project-name>/
│       ├── PRODUCT.md
│       ├── CLAUDE.md
│       ├── .workflow/
│       ├── src/
│       └── tests/
│
├── CLAUDE.md                        # Orchestrator context
├── GEMINI.md                        # Gemini context
├── .cursor/rules                    # Cursor rules
├── pyproject.toml                   # Python project config
└── README.md                        # Project readme
```

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 4.0 | 2026-01-22 | Added Universal Agent Loop, updated test count to 1,250+ |
| 3.0 | 2026-01-21 | Added parallel workers, external projects, file boundaries |
| 2.0 | 2026-01-21 | Added LangGraph workflow, task-based execution |
| 1.0 | 2026-01-20 | Initial release with 5-phase workflow |

---

**End of Document**

*Conductor: Orchestrating AI Agents for Quality Software Development*
