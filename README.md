# Meta-Architect: Multi-Agent Development System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A **production-ready multi-agent orchestration system** that coordinates Claude Code, Cursor CLI, and Gemini CLI through a structured 5-phase workflow to implement features with built-in quality assurance.

## Table of Contents

- [How It Works](#how-it-works)
- [LangGraph Architecture](#langgraph-architecture)
- [The 5-Phase Workflow](#the-5-phase-workflow)
- [Agent Specializations](#agent-specializations)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Approval & Conflict Resolution](#approval--conflict-resolution)
- [CLI Reference](#cli-reference)
- [Python API](#python-api)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## How It Works

Meta-Architect solves the coordination problem for AI-assisted development by orchestrating three specialized agents through a proven workflow:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        User Request                                      │
│            "Implement JWT authentication from PRODUCT.md"                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CLAUDE CODE (Lead Orchestrator)                       │
│                                                                          │
│  Phase 1: Planning ──────────────────────────────────────────────────►  │
│            │                                                             │
│            ▼                                                             │
│  Phase 2: Validation ────────────────────────────────────────────────►  │
│            │                     ┌─────────────┐   ┌─────────────┐      │
│            │   parallel call ───►│   CURSOR    │   │   GEMINI    │      │
│            │                     │ Code Review │   │ Arch Review │      │
│            │                     └─────────────┘   └─────────────┘      │
│            ▼                            │                │               │
│         Feedback ◄──────────────────────┴────────────────┘               │
│            │                                                             │
│            ▼ (iterate if needed)                                         │
│  Phase 3: Implementation (TDD) ──────────────────────────────────────►  │
│            │                                                             │
│            ▼                                                             │
│  Phase 4: Verification ──────────────────────────────────────────────►  │
│            │                     ┌─────────────┐   ┌─────────────┐      │
│            │   parallel call ───►│   CURSOR    │   │   GEMINI    │      │
│            │                     │ Final Check │   │ Final Check │      │
│            │                     └─────────────┘   └─────────────┘      │
│            ▼                                                             │
│  Phase 5: Completion ────────────────────────────────────────────────►  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                        Feature Implemented + Documented
```

### Key Innovations

| Feature | Description |
|---------|-------------|
| **Live Orchestration** | Claude Code coordinates in real-time within your project |
| **Parallel Reviews** | Cursor and Gemini run simultaneously for faster feedback |
| **Shared Context** | All agents read the same project files and state |
| **Iterative Refinement** | Automatic feedback loops until quality thresholds are met |
| **TDD Enforcement** | Tests written before implementation in Phase 3 |
| **Git Integration** | Auto-commits after each phase with rollback capability |
| **State Persistence** | Resume interrupted workflows from any phase |

---

## LangGraph Architecture

The orchestration system uses **LangGraph** for graph-based workflow management with native parallelism, checkpointing, and human-in-the-loop capabilities.

### Workflow Graph

```
┌──────────────────┐
│  prerequisites   │ ← Validate project setup
└────────┬─────────┘
         ▼
┌──────────────────┐
│    planning      │ ← Claude creates plan (Phase 1)
└────────┬─────────┘
         │
    ┌────┴────┐ (PARALLEL fan-out)
    ▼         ▼
┌────────┐ ┌────────┐
│ Cursor │ │ Gemini │ ← Validate plan (Phase 2)
│validate│ │validate│   READ-ONLY reviewers
└───┬────┘ └───┬────┘
    └────┬────┘ (fan-in)
         ▼
┌──────────────────┐
│validation_fan_in │ ← Merge feedback, route decision
└────────┬─────────┘
         │ conditional: continue → implementation
         │             retry → planning
         │             escalate → human_escalation
         ▼
┌──────────────────┐
│ implementation   │ ← Worker Claude writes code (Phase 3)
└────────┬─────────┘   SEQUENTIAL - single writer
         │
    ┌────┴────┐ (PARALLEL fan-out)
    ▼         ▼
┌────────┐ ┌────────┐
│ Cursor │ │ Gemini │ ← Review code (Phase 4)
│ review │ │ review │   READ-ONLY reviewers
└───┬────┘ └───┬────┘
    └────┬────┘ (fan-in)
         ▼
┌──────────────────┐
│verification_fan_in│ ← Merge reviews, route decision
└────────┬─────────┘
         ▼
┌──────────────────┐
│   completion     │ ← Generate summary (Phase 5)
└──────────────────┘
```

### Key Safety Guarantees

| Guarantee | Implementation |
|-----------|----------------|
| **No file conflicts** | Only `implementation` node writes files; Cursor/Gemini are read-only |
| **Human escalation** | `interrupt()` pauses workflow for human input when needed |
| **Checkpoint/resume** | SqliteSaver persists state for recovery from any point |
| **Transient error handling** | Exponential backoff with jitter for recoverable errors |
| **Worker clarification** | Workers can request human answers for ambiguous requirements |

### Running with LangGraph

```bash
# Start new workflow with LangGraph
python -m orchestrator --project my-feature --use-langgraph

# Resume from checkpoint
python -m orchestrator --project my-feature --resume --use-langgraph

# Run tests
python -m pytest tests/test_langgraph.py -v
```

### State Schema

The workflow uses typed state with reducers for parallel merge:

```python
class WorkflowState(TypedDict):
    project_dir: str
    project_name: str
    current_phase: int
    phase_status: dict[str, PhaseState]
    plan: Optional[dict]
    validation_feedback: Annotated[dict, _merge_feedback]  # Parallel merge
    verification_feedback: Annotated[dict, _merge_feedback]
    implementation_result: Optional[dict]
    next_decision: Optional[WorkflowDecision]  # continue|retry|escalate|abort
    errors: Annotated[list[dict], operator.add]  # Append-only
```

---

## The 5-Phase Workflow

### Phase 1: Planning (Claude)

Claude reads your feature specification and creates a detailed implementation plan.

**Input:** `PRODUCT.md` (your feature specification)

**Output:**
- `plan.json` - Structured plan with components, dependencies, test strategy
- `PLAN.md` - Human-readable plan document

**Example plan.json structure:**
```json
{
  "plan_name": "JWT Authentication Service",
  "summary": "Implement secure JWT-based authentication",
  "phases": [
    {
      "name": "Core Auth Module",
      "tasks": ["Create user model", "Implement password hashing", "Generate JWT tokens"],
      "dependencies": ["bcrypt", "jsonwebtoken"]
    }
  ],
  "test_strategy": {
    "approach": "TDD",
    "test_commands": ["pytest tests/ -v"]
  }
}
```

---

### Phase 2: Validation (Cursor + Gemini, Parallel)

Both agents review the plan simultaneously, each focusing on their specialization.

**Cursor Reviews:**
- Security vulnerabilities
- Code quality concerns
- Test coverage gaps
- Maintainability issues

**Gemini Reviews:**
- Architecture patterns
- Scalability considerations
- Design trade-offs
- System health impact

**Output:**
- `cursor-feedback.json` - Cursor's review with score and concerns
- `gemini-feedback.json` - Gemini's review with score and concerns
- `consolidated-feedback.json` - Merged feedback
- `approval-result.json` - Approval decision

**Approval Policy:** `NO_BLOCKERS`
- No high-severity blocking issues
- Combined score >= 6.0/10

**If not approved:** Claude revises the plan and re-submits (max 3 iterations)

---

### Phase 3: Implementation (Claude, TDD)

Claude implements the feature following Test-Driven Development:

1. **Write failing tests first** - Define expected behavior
2. **Implement code** - Make tests pass
3. **Refactor** - Improve code while keeping tests green
4. **Verify** - Run full test suite

**Output:**
- Actual source code files
- Test files
- `implementation-results.json` - Summary of changes
- `test-results.json` - Test execution results

---

### Phase 4: Verification (Cursor + Gemini, Parallel)

Both agents review the implemented code for final approval.

**Cursor Verifies:**
- No security vulnerabilities introduced
- Code follows best practices
- Tests are comprehensive
- No regressions

**Gemini Verifies:**
- Architecture matches the plan
- No technical debt introduced
- Performance is acceptable
- Design patterns properly applied

**Output:**
- `cursor-review.json` - Final code review
- `gemini-review.json` - Final architecture review
- `verification-results.json` - Combined results
- `ready-to-merge.json` - Final approval status

**Approval Policy:** `ALL_MUST_APPROVE`
- Both agents must explicitly approve
- Combined score >= 7.0/10
- No blocking issues

**If not approved:** Claude fixes issues and re-verifies

---

### Phase 5: Completion (Claude)

Generate final documentation and metrics.

**Output:**
- `COMPLETION.md` - Workflow summary document
- `metrics.json` - Performance and quality metrics
- Final state update

---

## Agent Specializations

| Agent | CLI Tool | Role | Expertise Areas |
|-------|----------|------|-----------------|
| **Claude Code** | `claude` | Lead Orchestrator | Planning, implementation, coordination, TDD |
| **Cursor Agent** | `cursor` | Code Reviewer | Security (0.8), code quality (0.7), testing (0.7) |
| **Gemini Agent** | `gemini` | Architecture Reviewer | Architecture (0.7), scalability (0.8), performance (0.6) |

### Expertise Weights (for conflict resolution)

When agents disagree, the system uses weighted expertise:

| Area | Cursor Weight | Gemini Weight |
|------|--------------|---------------|
| Security | 0.8 | 0.2 |
| Code Quality | 0.7 | 0.3 |
| Testing | 0.7 | 0.3 |
| Architecture | 0.3 | 0.7 |
| Scalability | 0.2 | 0.8 |
| Performance | 0.4 | 0.6 |
| Maintainability | 0.6 | 0.4 |

---

## Installation

### Prerequisites

- Python 3.10+
- Git
- AI CLI tools:
  - **Claude Code CLI** (`claude`) - Required
  - **Cursor CLI** (`cursor`) - Optional but recommended
  - **Gemini CLI** (`gemini`) - Optional but recommended

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/meta-architect.git
cd meta-architect

# Create virtual environment (optional)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "from orchestrator import Orchestrator; print('OK')"
```

---

## Quick Start

### 1. Initialize Your Project

```bash
bash scripts/init-multi-agent.sh /path/to/your/project
```

This creates the workflow structure in your project.

### 2. Define Your Feature

Edit `PRODUCT.md` with your feature specification:

```markdown
# Product Specification

## Feature Name
User Authentication System

## Summary
Implement JWT-based authentication with login, registration, and token refresh.

## Goals
- Secure user registration with email verification
- JWT token generation with configurable expiry
- Token refresh mechanism
- Password reset flow

## Technical Requirements
- Use bcrypt for password hashing
- Store tokens in HTTP-only cookies
- Implement rate limiting on auth endpoints

## Test Strategy
- Unit tests for all auth functions
- Integration tests for API endpoints
- Security tests for token validation
```

### 3. Start the Workflow

```bash
cd /path/to/your/project
claude
```

In Claude Code, say:
```
Implement the feature from PRODUCT.md
```

Or use the skill directly:
```
/orchestrate
```

Claude will automatically execute all 5 phases.

### 4. Monitor Progress

Check status at any time:
```bash
python -m orchestrator --status
```

Or in Claude Code:
```
/phase-status
```

---

## Project Structure

After initialization, your project will have:

```
your-project/
├── PRODUCT.md              # Your feature specification (edit this!)
├── AGENTS.md               # Workflow rules (source of truth)
├── CLAUDE.md               # Claude-specific instructions
├── GEMINI.md               # Gemini-specific instructions
│
├── .claude/
│   └── system.md           # Claude system prompt
├── .cursor/
│   └── rules               # Cursor rules
├── .gemini/
│   └── GEMINI.md           # Gemini context
│
├── scripts/
│   ├── call-cursor.sh      # Invoke Cursor CLI
│   ├── call-gemini.sh      # Invoke Gemini CLI
│   └── prompts/            # Prompt templates
│
└── .workflow/
    ├── state.json          # Workflow state machine
    ├── coordination.log    # Human-readable logs
    ├── coordination.jsonl  # Structured JSON logs
    │
    └── phases/
        ├── planning/       # Phase 1 outputs
        │   ├── plan.json
        │   └── PLAN.md
        ├── validation/     # Phase 2 outputs
        │   ├── cursor-feedback.json
        │   ├── gemini-feedback.json
        │   └── consolidated-feedback.json
        ├── implementation/ # Phase 3 outputs
        │   ├── implementation-results.json
        │   └── test-results.json
        ├── verification/   # Phase 4 outputs
        │   ├── cursor-review.json
        │   ├── gemini-review.json
        │   └── ready-to-merge.json
        └── completion/     # Phase 5 outputs
            ├── COMPLETION.md
            └── metrics.json
```

### Meta-Architect Source Structure

```
meta-architect/
├── orchestrator/           # Python orchestration library
│   ├── __init__.py
│   ├── orchestrator.py     # Main Orchestrator class
│   ├── agents/             # Agent CLI wrappers
│   │   ├── base.py         # BaseAgent class
│   │   ├── claude.py       # ClaudeAgent
│   │   ├── cursor.py       # CursorAgent
│   │   └── gemini.py       # GeminiAgent
│   ├── phases/             # Phase implementations (legacy)
│   │   ├── base.py         # BasePhase class
│   │   ├── phase1_planning.py
│   │   ├── phase2_validation.py
│   │   ├── phase3_implementation.py
│   │   ├── phase4_verification.py
│   │   └── phase5_completion.py
│   ├── langgraph/          # LangGraph workflow (recommended)
│   │   ├── workflow.py     # Graph assembly, entry point
│   │   ├── state.py        # TypedDict state schema, reducers
│   │   ├── nodes/          # Node implementations
│   │   │   ├── prerequisites.py
│   │   │   ├── planning.py
│   │   │   ├── validation.py
│   │   │   ├── implementation.py
│   │   │   ├── verification.py
│   │   │   ├── escalation.py
│   │   │   └── completion.py
│   │   ├── routers/        # Conditional edge logic
│   │   │   ├── validation.py
│   │   │   └── verification.py
│   │   └── integrations/   # Adapters for existing utils
│   │       ├── approval.py
│   │       ├── conflict.py
│   │       └── state.py
│   └── utils/              # Utilities
│       ├── state.py        # StateManager
│       ├── logging.py      # OrchestrationLogger
│       ├── approval.py     # ApprovalEngine
│       ├── conflict_resolution.py
│       ├── context.py      # ContextManager (drift detection)
│       ├── git_operations.py  # GitOperationsManager
│       ├── resilience.py   # AsyncCircuitBreaker, RetryPolicy
│       └── validation.py   # Feedback validation
├── scripts/
│   ├── init-multi-agent.sh # Project initialization
│   ├── call-cursor.sh      # Cursor CLI wrapper
│   ├── call-gemini.sh      # Gemini CLI wrapper
│   ├── create-project.py   # Create new projects
│   ├── sync-rules.py       # Sync shared rules to agents
│   └── sync-project-templates.py  # Sync templates to projects
├── shared-rules/           # Shared rules for all agents
│   ├── core-rules.md
│   ├── coding-standards.md
│   ├── guardrails.md
│   ├── cli-reference.md
│   ├── lessons-learned.md
│   └── agent-overrides/    # Agent-specific extensions
├── project-templates/      # Project templates
├── projects/               # Project containers
├── schemas/                # JSON validation schemas
├── tests/                  # Test suite
│   ├── test_langgraph.py   # LangGraph tests (57 tests)
│   └── ...
└── examples/               # Example projects
```

---

## Configuration

### Workflow State (`state.json`)

```json
{
  "project_name": "my-feature",
  "current_phase": 2,
  "iteration_count": 1,
  "phases": {
    "planning": { "status": "completed", "attempts": 1 },
    "validation": { "status": "in_progress", "attempts": 1 },
    "implementation": { "status": "pending", "attempts": 0 },
    "verification": { "status": "pending", "attempts": 0 },
    "completion": { "status": "pending", "attempts": 0 }
  },
  "git_commits": [
    { "phase": 1, "hash": "abc123", "message": "[orchestrator] Phase 1: planning complete" }
  ]
}
```

### Phase Status Values

| Status | Description |
|--------|-------------|
| `pending` | Not yet started |
| `in_progress` | Currently executing |
| `completed` | Successfully finished |
| `failed` | Failed (will retry) |
| `blocked` | Blocked by issues |

---

## Approval & Conflict Resolution

### Approval Policies

| Policy | Description | Default Phase |
|--------|-------------|---------------|
| `NO_BLOCKERS` | No blocking issues, score >= 6.0 | Phase 2 |
| `ALL_MUST_APPROVE` | Both agents approve, score >= 7.0 | Phase 4 |
| `WEIGHTED_SCORE` | Weighted average meets threshold | Custom |
| `MAJORITY` | At least one agent approves | Custom |

### Conflict Resolution Strategies

When Cursor and Gemini disagree:

| Strategy | Description |
|----------|-------------|
| `WEIGHTED` | Use expertise weights for the area (default) |
| `CONSERVATIVE` | Take the more cautious position |
| `OPTIMISTIC` | Take the more permissive position |
| `DEFER_TO_LEAD` | Claude decides |
| `UNANIMOUS` | Both must agree or escalate |
| `ESCALATE` | Require human decision |

---

## CLI Reference

### Python Orchestrator

```bash
# Start workflow from phase 1
python -m orchestrator --start

# Resume from last incomplete phase
python -m orchestrator --resume

# Start from specific phase
python -m orchestrator --phase 3

# Check current status
python -m orchestrator --status

# Health check (agent availability)
python -m orchestrator --health

# Reset all phases
python -m orchestrator --reset

# Rollback to before phase N
python -m orchestrator --rollback 3

# Skip validation phase
python -m orchestrator --start --skip-validation

# Disable auto-commit
python -m orchestrator --start --no-commit

# Set max retries
python -m orchestrator --start --max-retries 5

# Debug output
python -m orchestrator --start --debug
```

### Agent Scripts

```bash
# Call Cursor for code review
bash scripts/call-cursor.sh <prompt-file> <output-file> [project-dir]

# Call Gemini for architecture review
bash scripts/call-gemini.sh <prompt-file> <output-file> [project-dir]
```

### Claude Code Skills

| Skill | Purpose |
|-------|---------|
| `/orchestrate` | Start or resume the 5-phase workflow |
| `/phase-status` | Show current workflow status |
| `/validate` | Run Phase 2 validation manually |
| `/verify` | Run Phase 4 verification manually |
| `/resolve-conflict` | Resolve agent disagreements |

---

## Python API

### Basic Usage

```python
from orchestrator import Orchestrator

# Initialize
orch = Orchestrator(
    project_dir="/path/to/project",
    max_retries=3,
    auto_commit=True,
)

# Run full workflow
result = orch.run(start_phase=1, end_phase=5)
print(f"Success: {result['success']}")

# Resume interrupted workflow
result = orch.resume()

# Check status
status = orch.status()
print(f"Current phase: {status['current_phase']}")

# Health check
health = orch.health_check()
print(f"Agents: {health['agents']}")

# Rollback
result = orch.rollback_to_phase(3)
```

### State Management

```python
from orchestrator.utils import StateManager, PhaseStatus

state = StateManager("/path/to/project")
state.load()

# Get phase info
phase = state.get_phase(2)
print(f"Status: {phase.status}")
print(f"Attempts: {phase.attempts}")

# Check if can retry
if state.can_retry(2):
    state.reset_phase(2)

# Get summary
summary = state.get_summary()
```

### Approval Engine

```python
from orchestrator.utils import ApprovalEngine, ApprovalConfig, ApprovalPolicy

engine = ApprovalEngine()

# Evaluate validation feedback
result = engine.evaluate_for_validation(cursor_feedback, gemini_feedback)
print(f"Approved: {result.approved}")
print(f"Reasoning: {result.reasoning}")

# Custom configuration
config = ApprovalConfig(
    policy=ApprovalPolicy.ALL_MUST_APPROVE,
    minimum_score=8.0,
)
result = engine.evaluate_for_validation(
    cursor_feedback, gemini_feedback, config=config
)
```

### Conflict Resolution

```python
from orchestrator.utils import ConflictResolver, ResolutionStrategy

resolver = ConflictResolver(default_strategy=ResolutionStrategy.WEIGHTED)

# Detect and resolve conflicts
result = resolver.resolve_all(cursor_feedback, gemini_feedback)
print(f"Conflicts: {len(result.conflicts)}")
print(f"Unresolved: {result.unresolved_count}")

# Get consensus
consensus = resolver.get_consensus_recommendation(
    cursor_feedback, gemini_feedback
)
```

---

## Troubleshooting

### Agent CLI Not Found

```
Error: cursor CLI not found
```

Install missing CLI tools or set environment variables:
```bash
export CURSOR_CLI_PATH=/path/to/cursor
export GEMINI_CLI_PATH=/path/to/gemini
```

The workflow can proceed with available agents.

### Context Drift Detected

```
WARNING: Context drift detected - AGENTS.md modified
```

A tracked file changed mid-workflow. Options:
- Continue (default): Warning logged, workflow proceeds
- Sync: Update checksums with `state.sync_context()`
- Reset: Start workflow from Phase 1

### Max Iterations Reached

After 3 failed validation/verification attempts:
- Claude summarizes blocking issues
- Asks for human guidance
- Options: continue, abort, or modify approach

### Workflow Stuck

```bash
# Check what's happening
python -m orchestrator --status

# View logs
cat .workflow/coordination.log

# Reset specific phase
python -m orchestrator --reset

# Or rollback
python -m orchestrator --rollback 2
```

### Tests Failing

If Phase 3 tests fail:
1. Check `.workflow/phases/implementation/test-results.json`
2. Review the error messages
3. Claude will attempt to fix and re-run (up to max retries)

---

## Performance Optimizations

The system includes several performance optimizations:

| Optimization | Description |
|--------------|-------------|
| **Batched Git Operations** | Single subprocess for status+add+commit+hash |
| **Unified Timeouts** | No timeout stacking in parallel execution |
| **Streaming Subprocess** | Memory-efficient output capture with size limits |
| **Cached Repo Detection** | Git repo check cached after first call |
| **Parallel Agent Execution** | Cursor and Gemini run simultaneously |

See `OPTIMIZATION_BACKLOG.md` for future improvements.

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test modules
python -m pytest tests/test_orchestrator.py -v
python -m pytest tests/test_phases.py -v
python -m pytest tests/test_approval.py -v

# Run with coverage
python -m pytest tests/ --cov=orchestrator --cov-report=html
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Make your changes
4. Run tests (`python -m pytest tests/ -v`)
5. Commit (`git commit -m 'Add improvement'`)
6. Push (`git push origin feature/improvement`)
7. Open a Pull Request

---

Built with Claude Code, Cursor, and Gemini.
