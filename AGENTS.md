# Conductor Agent Registry

Complete inventory of all agents defined in the conductor codebase.

**Purpose**: Reference for prompt optimization and agent management.

**Last Updated**: 2026-01-23

---

## Table of Contents

1. [CLI Agent Wrappers](#1-cli-agent-wrappers)
2. [Specialized Agents](#2-specialized-agents)
3. [Universal Adapter Layer](#3-universal-adapter-layer)
4. [Specialist Agent Registry (A01-A12)](#4-specialist-agent-registry-a01-a12)
5. [LangGraph Workflow Nodes](#5-langgraph-workflow-nodes)
6. [Claude Code Skills](#6-claude-code-skills)
7. [Supporting Components](#7-supporting-components)

---

## 1. CLI Agent Wrappers

Core agent classes that wrap CLI tools for orchestration.

| ID | Name | File | CLI Command |
|----|------|------|-------------|
| CLI-01 | ClaudeAgent | `orchestrator/agents/claude_agent.py` | `claude` |
| CLI-02 | CursorAgent | `orchestrator/agents/cursor_agent.py` | `cursor-agent` |
| CLI-03 | GeminiAgent | `orchestrator/agents/gemini_agent.py` | `gemini` |
| CLI-00 | BaseAgent | `orchestrator/agents/base.py` | (abstract) |

### CLI-01: ClaudeAgent

**Identifier**: `ClaudeAgent`
**File**: `orchestrator/agents/claude_agent.py`
**CLI**: `claude`

**Description**: Primary implementation agent. Wrapper for Claude Code CLI with enhanced features including plan mode detection, session continuity for iterative refinement, JSON schema validation, and budget control.

**Capabilities**:
- Plan mode detection (`--permission-mode plan`) for tasks touching ≥3 files
- Session continuity (`--resume`, `--session-id`) across Ralph loop iterations
- JSON schema validation for structured output
- Budget control per-invocation (`--max-budget-usd`)
- Fallback model configuration (`--fallback-model sonnet`)

**Key Methods**:
- `run_planning()` - Execute planning with plan mode
- `run_implementation()` - Execute implementation task
- `run_task()` - High-level task execution
- `should_use_plan_mode()` - Auto-detect plan mode need

**Context Files Read**: `CLAUDE.md`, `CONTEXT.md`

---

### CLI-02: CursorAgent

**Identifier**: `CursorAgent`
**File**: `orchestrator/agents/cursor_agent.py`
**CLI**: `cursor-agent`

**Description**: Security-focused code reviewer. Wrapper for Cursor CLI specializing in security validation and per-file issue detection.

**Capabilities**:
- Model selection (codex-5.2, composer)
- Plan validation with security focus (0.8 weight in conflicts)
- Code review with per-file issue detection
- OWASP Top 10 vulnerability scanning
- Output as structured JSON

**Key Methods**:
- `run_validation()` - Validate plan for security issues
- `run_code_review()` - Review code for vulnerabilities

**Context Files Read**: `.cursor/rules`, `AGENTS.md`

---

### CLI-03: GeminiAgent

**Identifier**: `GeminiAgent`
**File**: `orchestrator/agents/gemini_agent.py`
**CLI**: `gemini`

**Description**: Architecture reviewer. Wrapper for Gemini CLI specializing in architectural validation, design patterns, and scalability assessment.

**Capabilities**:
- Model selection (gemini-2.0-flash, gemini-2.0-pro)
- Architectural validation with design pattern analysis
- Architecture review (0.7 weight in conflicts)
- Scalability and technical debt assessment
- Modularity and maintainability scoring

**Key Methods**:
- `run_validation()` - Validate architectural decisions
- `run_architecture_review()` - Full architecture review

**Context Files Read**: `GEMINI.md`

---

### CLI-00: BaseAgent (Abstract)

**Identifier**: `BaseAgent`
**File**: `orchestrator/agents/base.py`
**CLI**: N/A (abstract base class)

**Description**: Abstract base class providing common CLI wrapper functionality for all agent implementations.

**Capabilities**:
- Command execution with subprocess management
- Timeout handling (phase-specific: 5-30 minutes)
- JSON output parsing
- Audit trail integration
- Schema validation
- Error handling and CLI availability checking

**Key Methods**:
- `run()` - Execute agent command
- `build_command()` - Build CLI command array
- `validate_output()` - Validate against schema
- `check_available()` - Check if CLI is available

---

## 2. Specialized Agents

Purpose-built agents for specific tasks.

| ID | Name | File | Purpose |
|----|------|------|---------|
| SPEC-01 | FixerAgent | `orchestrator/fixer/agent.py` | Self-healing error recovery |
| SPEC-02 | ResearchAgent | `orchestrator/langgraph/nodes/research_phase.py` | Pre-planning codebase analysis |

### SPEC-01: FixerAgent

**Identifier**: `FixerAgent`
**File**: `orchestrator/fixer/agent.py`

**Description**: Autonomous error detection and fixing agent with circuit breaker pattern. Attempts to fix errors automatically before escalating to human intervention.

**Capabilities**:
- Error triage with categorization (syntax, import, test, runtime, etc.)
- Root cause diagnosis via stack trace analysis
- Fix plan generation with multiple strategies
- Fix validation (pre/post)
- Circuit breaker for failure prevention
- Known fixes database lookup
- Security notification handling

**Key Methods**:
- `attempt_fix()` - Main entry point for fix attempt
- `triage_error()` - Categorize and prioritize error
- `diagnose()` - Determine root cause
- `create_plan()` - Generate fix plan
- `apply_fix()` - Apply fix to codebase

**Integration**: Used in error handling path before human escalation

---

### SPEC-02: ResearchAgent

**Identifier**: `ResearchAgent`
**File**: `orchestrator/langgraph/nodes/research_phase.py` (dataclass lines 32-39)

**Description**: Parallel research agents that investigate the codebase before planning begins. Provides data-driven insights for better plan generation.

**Sub-Agents**:
| Sub-ID | Name | Focus |
|--------|------|-------|
| SPEC-02a | Tech Stack Analyzer | Languages, frameworks, libraries, versions, constraints |
| SPEC-02b | Codebase Pattern Analyzer | Architecture patterns, naming conventions, testing patterns |

**Capabilities**:
- Parallel execution (2 agents simultaneously)
- 120-second timeout per agent
- JSON output with technical stack and code patterns
- Informs planning phase with concrete data

**Output Structure**:
```json
{
  "tech_stack": { "languages": [], "frameworks": [], "libraries": [] },
  "patterns": { "architecture": "", "naming": "", "testing": "" }
}
```

---

## 3. Universal Adapter Layer

Uniform interface for running any agent in iterative loops.

| ID | Name | File | Target CLI |
|----|------|------|------------|
| ADAPT-00 | AgentAdapter | `orchestrator/agents/adapter.py` | (abstract) |
| ADAPT-01 | ClaudeAdapter | `orchestrator/agents/adapter.py` | `claude` |
| ADAPT-02 | CursorAdapter | `orchestrator/agents/adapter.py` | `cursor-agent` |
| ADAPT-03 | GeminiAdapter | `orchestrator/agents/adapter.py` | `gemini` |

### ADAPT-00: AgentAdapter (Abstract)

**Identifier**: `AgentAdapter`
**File**: `orchestrator/agents/adapter.py`

**Description**: Abstract base class providing uniform interface for running any agent in iterative TDD loops (Ralph Wiggum pattern).

**Key Methods**:
- `build_command()` - Build CLI command for iteration
- `detect_completion()` - Check if agent signaled done
- `run_iteration()` - Execute single loop iteration

---

### ADAPT-01: ClaudeAdapter

**Identifier**: `ClaudeAdapter`
**File**: `orchestrator/agents/adapter.py`

**Description**: Claude-specific adapter for iterative execution.

**Completion Pattern**: `<promise>DONE</promise>`
**Model Selection**: sonnet, opus, haiku

---

### ADAPT-02: CursorAdapter

**Identifier**: `CursorAdapter`
**File**: `orchestrator/agents/adapter.py`

**Description**: Cursor-specific adapter for iterative execution.

**Completion Pattern**: `{"status": "done"}` in JSON output
**Model Selection**: codex-5.2, composer

---

### ADAPT-03: GeminiAdapter

**Identifier**: `GeminiAdapter`
**File**: `orchestrator/agents/adapter.py`

**Description**: Gemini-specific adapter for iterative execution.

**Completion Pattern**: `DONE` or `COMPLETE` in text output
**Model Selection**: gemini-2.0-flash, gemini-2.0-pro

---

## 4. Specialist Agent Registry (A01-A12)

Pre-configured specialist agents with defined roles and file access boundaries.

**Registry File**: `orchestrator/registry/agents.py`

| ID | Name | CLI | Role | Writable Paths |
|----|------|-----|------|----------------|
| A01 | Planner | claude | Break features into tasks | Read-only |
| A02 | Architect | gemini | Review architecture/design | Read-only |
| A03 | Test Writer | claude | Write failing tests (TDD) | `tests/**/*` |
| A04 | Implementer | claude | Implement to pass tests | `src/**/*`, `lib/**/*` |
| A05 | Bug Fixer | cursor | Diagnose and fix bugs | `src/**/*`, `lib/**/*`, `tests/**/*` |
| A06 | Refactorer | gemini | Refactor (keep tests green) | `src/**/*`, `lib/**/*` |
| A07 | Security Reviewer | cursor | OWASP Top 10 review | Read-only |
| A08 | Code Reviewer | gemini | Code quality & patterns | Read-only |
| A09 | Documentation Writer | claude | Write and update docs | `docs/**/*`, `*.md` |
| A10 | Integration Tester | claude | E2E, BDD, Playwright | `tests/**/*`, `e2e/**/*` |
| A11 | DevOps Engineer | cursor | CI/CD, deployment | `.github/**/*`, `*.yml` |
| A12 | UI Designer | claude | UI components & styling | `src/components/**/*`, `*.css`, `*.tsx` |
| A13 | Quality Gate | cursor | Code quality checks | Read-only |
| A14 | Dependency Checker | claude | Dependency updates | `package.json`, `Dockerfile` |
| A15 | Watchdog Agent | python | Runtime monitoring | Read-only |

### A01: Planner

**Identifier**: `A01`
**Name**: Planner
**CLI**: `claude`

**Description**: Breaks feature specifications into discrete, implementable tasks with clear acceptance criteria and dependencies.

**Responsibilities**:
- Parse PRODUCT.md requirements
- Create task breakdown with dependencies
- Estimate complexity scores
- Define file boundaries per task

**File Access**: Read-only

---

### A02: Architect

**Identifier**: `A02`
**Name**: Architect
**CLI**: `gemini`

**Description**: Reviews architectural decisions and validates design patterns against best practices.

**Responsibilities**:
- Validate architecture decisions
- Check design pattern usage
- Assess scalability implications
- Review module boundaries

**File Access**: Read-only

---

### A03: Test Writer

**Identifier**: `A03`
**Name**: Test Writer
**CLI**: `claude`

**Description**: Writes failing tests first (TDD red phase) based on acceptance criteria.

**Responsibilities**:
- Write unit tests from acceptance criteria
- Create test fixtures and mocks
- Ensure tests fail initially (red phase)
- Cover edge cases and error conditions

**File Access**: `tests/**/*`

---

### A04: Implementer

**Identifier**: `A04`
**Name**: Implementer
**CLI**: `claude`

**Description**: Implements code to make failing tests pass (TDD green phase).

**Responsibilities**:
- Write minimal code to pass tests
- Follow existing code patterns
- Maintain code quality standards
- Keep implementation focused

**File Access**: `src/**/*`, `lib/**/*`

---

### A05: Bug Fixer

**Identifier**: `A05`
**Name**: Bug Fixer
**CLI**: `cursor`

**Description**: Diagnoses and fixes bugs with security awareness.

**Responsibilities**:
- Analyze error logs and stack traces
- Identify root cause
- Implement targeted fixes
- Verify fix doesn't introduce regressions

**File Access**: `src/**/*`, `lib/**/*`, `tests/**/*`

---

### A06: Refactorer

**Identifier**: `A06`
**Name**: Refactorer
**CLI**: `gemini`

**Description**: Refactors code while keeping all tests green.

**Responsibilities**:
- Improve code structure
- Reduce duplication
- Enhance readability
- Maintain test coverage

**File Access**: `src/**/*`, `lib/**/*`

---

### A07: Security Reviewer

**Identifier**: `A07`
**Name**: Security Reviewer
**CLI**: `cursor`

**Description**: Reviews code for OWASP Top 10 and other security vulnerabilities.

**Responsibilities**:
- Scan for injection vulnerabilities
- Check authentication/authorization
- Review cryptographic usage
- Validate input sanitization

**File Access**: Read-only

---

### A08: Code Reviewer

**Identifier**: `A08`
**Name**: Code Reviewer
**CLI**: `gemini`

**Description**: Reviews code quality, patterns, and maintainability.

**Responsibilities**:
- Check code style consistency
- Review naming conventions
- Assess complexity and readability
- Verify documentation

**File Access**: Read-only

---

### A09: Documentation Writer

**Identifier**: `A09`
**Name**: Documentation Writer
**CLI**: `claude`

**Description**: Creates and maintains project documentation.

**Responsibilities**:
- Write README files
- Create API documentation
- Document architecture decisions
- Maintain changelog

**File Access**: `docs/**/*`, `*.md`

---

### A10: Integration Tester

**Identifier**: `A10`
**Name**: Integration Tester
**CLI**: `claude`

**Description**: Writes end-to-end and integration tests.

**Responsibilities**:
- Create E2E test scenarios
- Write BDD specifications
- Implement Playwright tests
- Test API integrations

**File Access**: `tests/**/*`, `e2e/**/*`

---

### A11: DevOps Engineer

**Identifier**: `A11`
**Name**: DevOps Engineer
**CLI**: `cursor`

**Description**: Manages CI/CD pipelines and deployment configurations.

**Responsibilities**:
- Configure GitHub Actions
- Set up deployment workflows
- Manage infrastructure as code
- Optimize build pipelines

**File Access**: `.github/**/*`, `*.yml`

---

### A12: UI Designer

**Identifier**: `A12`
**Name**: UI Designer
**CLI**: `claude`

**Description**: Creates and styles UI components.

**Responsibilities**:
- Build React/Vue components
- Implement responsive designs
- Apply styling (CSS/Tailwind)
- Ensure accessibility

**File Access**: `src/components/**/*`, `*.css`, `*.tsx`

---

### A13: Quality Gate

**Identifier**: `A13`
**Name**: Quality Gate
**CLI**: `cursor`

**Description**: Enforces strict code quality standards, naming conventions, and structure.

**Responsibilities**:
- Enforce TypeScript strict mode
- Check naming conventions
- Validate project structure

**File Access**: Read-only

---

### A14: Dependency Checker

**Identifier**: `A14`
**Name**: Dependency Checker
**CLI**: `claude`

**Description**: monitors and updates project dependencies.

**Responsibilities**:
- Check for outdated packages
- Audit security vulnerabilities
- Propose version upgrades

**File Access**: `package.json`, `Dockerfile`

---

### A15: Watchdog Agent

**Identifier**: `A15`
**Name**: Watchdog Agent
**CLI**: `python`

**Description**: Proactive runtime error monitoring and self-healing.

**Responsibilities**:
- Monitor error logs
- Trigger FixerAgent on new errors
- Bridge runtime to self-healing

**File Access**: Read-only (triggers FixerAgent)

---

## 5. LangGraph Workflow Nodes

Agent-like components that execute as workflow nodes.

| ID | Name | File | Purpose |
|----|------|------|---------|
| NODE-01 | DiscussPhase | `nodes/discuss_phase.py` | Capture developer preferences |
| NODE-02 | ResearchPhase | `nodes/research_phase.py` | Pre-planning codebase analysis |
| NODE-03 | ImplementTask | `nodes/implement_task.py` | Spawn worker for implementation |
| NODE-04 | FixerTriage | `nodes/fixer_triage.py` | Route errors to fixer or human |
| NODE-05 | FixerDiagnose | `nodes/fixer_diagnose.py` | Root cause analysis |
| NODE-06 | FixerValidate | `nodes/fixer_validate.py` | Pre/post fix validation |
| NODE-07 | FixerApply | `nodes/fixer_apply.py` | Apply fixes to code |
| NODE-08 | FixerVerify | `nodes/fixer_verify.py` | Verify fix effectiveness |

### NODE-01: DiscussPhase

**Identifier**: `discuss_phase_node`
**File**: `orchestrator/langgraph/nodes/discuss_phase.py`

**Description**: Captures developer preferences before planning through structured Q&A.

**Captures**:
- Library preferences
- Architecture decisions
- Testing philosophy
- Error handling approach
- Code style preferences

**Output**: `CONTEXT.md` file with captured preferences

---

### NODE-02: ResearchPhase

**Identifier**: `research_phase_node`
**File**: `orchestrator/langgraph/nodes/research_phase.py`

**Description**: Spawns parallel research agents to analyze codebase before planning.

**Spawns**: Tech Stack Analyzer + Codebase Pattern Analyzer (parallel)

---

### NODE-03: ImplementTask

**Identifier**: `implement_task_node`
**File**: `orchestrator/langgraph/nodes/implement_task.py`

**Description**: Spawns worker Claude for task implementation. Supports both Ralph Wiggum loop (iterative until tests pass) and Unified Loop (any agent).

**Features**:
- Scoped execution (workers see only task-relevant files)
- Context from CONTEXT.md and research findings
- TDD enforcement

---

### NODE-04: FixerTriage

**Identifier**: `fixer_triage_node`
**File**: `orchestrator/langgraph/nodes/fixer_triage.py`

**Description**: Routes errors to FixerAgent or escalates to human based on circuit breaker status and error limits.

**Decision Logic**:
- Check circuit breaker status
- Evaluate per-error retry limits
- Consider per-session error limits
- Route to fixer or escalate

---

### NODE-05 to NODE-08: Fixer Pipeline

**Files**: `fixer_diagnose.py`, `fixer_validate.py`, `fixer_apply.py`, `fixer_verify.py`

**Description**: Multi-stage error recovery pipeline for autonomous error handling.

**Pipeline Flow**:
1. **Diagnose**: Analyze stack trace, identify root cause
2. **Validate**: Pre-fix validation
3. **Apply**: Apply fix to codebase
4. **Verify**: Post-fix validation and test execution

---

## 6. Claude Code Skills

Declarative skills for high-level workflow orchestration.

**Location**: `.claude/skills/*/SKILL.md`

| ID | Name | Skill Command | Purpose |
|----|------|---------------|---------|
| SKILL-01 | Orchestrate | `/orchestrate` | Main workflow orchestration |
| SKILL-02 | Plan Feature | `/plan` | Planning phase with Task tool |
| SKILL-03 | Validate Plan | `/validate` | Parallel Cursor + Gemini validation |
| SKILL-04 | Implement Task | `/task` | TDD implementation via Task tool |
| SKILL-05 | Verify Code | `/verify` | Parallel code review |
| SKILL-06 | Call Cursor | (internal) | Cursor CLI wrapper |
| SKILL-07 | Call Gemini | (internal) | Gemini CLI wrapper |
| SKILL-08 | Resolve Conflict | `/resolve-conflict` | Conflict resolution |
| SKILL-09 | Phase Status | `/phase-status` | Show workflow progress |
| SKILL-10 | List Projects | `/list-projects` | Project listing |
| SKILL-11 | Sync Rules | `/sync-rules` | Sync shared context rules |
| SKILL-12 | Add Lesson | `/add-lesson` | Add to lessons learned |
| SKILL-13 | Discover | `/discover` | Read docs, create PRODUCT.md |
| SKILL-14 | Status | `/status` | Show current workflow status |
| SKILL-15 | Git Atomic | `/git-atomic` | Create atomic commits by dependency |
| SKILL-16 | Git Conventional | `/git-msg` | Create conventional commit messages |
| SKILL-17 | Git Helper | `/git-help` | Handle rebase/merge/hooks |
| SKILL-18 | TDD Overnight | `/tdd-run` | Autonomous TDD loop |
| SKILL-19 | Write Test | `/write-test` | Generate unit/integration tests |
| SKILL-20 | E2E Test | `/e2e-test` | Generate E2E tests |
| SKILL-21 | Refactor Safe | `/refactor` | Safe refactoring workflow |
| SKILL-22 | Visualize | `/visualize` | Visual architecture explanation |
| SKILL-23 | TS Guardian | `/ts-check` | Enforce strict TypeScript rules |
| SKILL-24 | API Contract | `/make-contract` | Create Zod contracts |
| SKILL-25 | Frontend Guides | n/a | Frontend patterns reference |
| SKILL-26 | Debug Action | `/debug-action` | Debug GitHub Actions |
| SKILL-27 | Changelog | `/changelog` | Generate release notes |
| SKILL-28 | New Skill | `/new-skill` | Scaffold new skills |
| SKILL-29 | Eval Skill | `/eval-skill` | Evaluate skill performance |

### SKILL-01: Orchestrate

**Identifier**: `orchestrate`
**Command**: `/orchestrate --project <name>`
**File**: `.claude/skills/orchestrate/SKILL.md`

**Description**: Main entry point for running the full 5-phase workflow.

---

### SKILL-02: Plan Feature

**Identifier**: `plan`
**Command**: `/plan`
**File**: `.claude/skills/plan/SKILL.md`

**Description**: Execute planning phase using Task tool to spawn planning worker.

---

### SKILL-03: Validate Plan

**Identifier**: `validate`
**Command**: `/validate`
**File**: `.claude/skills/validate/SKILL.md`

**Description**: Run parallel Cursor + Gemini validation on plan.

---

### SKILL-04: Implement Task

**Identifier**: `task`
**Command**: `/task <task-id>`
**File**: `.claude/skills/task/SKILL.md`

**Description**: Implement specific task using TDD via Task tool worker.

---

### SKILL-05: Verify Code

**Identifier**: `verify`
**Command**: `/verify`
**File**: `.claude/skills/verify/SKILL.md`

**Description**: Run parallel Cursor + Gemini code review.

---

### SKILL-08: Resolve Conflict

**Identifier**: `resolve-conflict`
**Command**: `/resolve-conflict`
**File**: `.claude/skills/resolve-conflict/SKILL.md`

**Description**: Resolve conflicts between Cursor and Gemini feedback using weighted scoring.

---

## 7. Supporting Components

Manager classes that support agent execution.

| ID | Name | File | Purpose |
|----|------|------|---------|
| SUPP-01 | SessionManager | `agents/session_manager.py` | Session continuity for loops |
| SUPP-02 | ErrorContextManager | `agents/error_context.py` | Learn from agent failures |
| SUPP-03 | BudgetManager | `agents/budget.py` | API cost control |
| SUPP-04 | AgentDispatcher | `dispatch/protocol.py` | Route tasks to agents |
| SUPP-05 | SpecialistRunner | `specialists/runner.py` | Load and execute specialists |

### SUPP-01: SessionManager

**Identifier**: `SessionManager`
**File**: `orchestrator/agents/session_manager.py`

**Description**: Manages session continuity for iterative agent execution (Ralph loop).

**Capabilities**:
- Create new sessions for tasks
- Resume existing sessions (preserves debugging context)
- Close sessions on completion
- Track session IDs per task

---

### SUPP-02: ErrorContextManager

**Identifier**: `ErrorContextManager`
**File**: `orchestrator/agents/error_context.py`

**Description**: Records agent failures and builds enhanced retry prompts.

**Capabilities**:
- Record errors with full context
- Classify error types
- Generate retry suggestions
- Build enhanced prompts with error history
- Clear errors on success

---

### SUPP-03: BudgetManager

**Identifier**: `BudgetManager`
**File**: `orchestrator/agents/budget.py`

**Description**: Tracks and enforces API costs per agent invocation.

**Capabilities**:
- Project-level budget limits
- Task-level budget limits
- Per-invocation budget limits
- Cost recording and tracking
- Budget exhaustion checks

---

### SUPP-04: AgentDispatcher

**Identifier**: `AgentDispatcher`
**File**: `orchestrator/dispatch/protocol.py`

**Description**: Routes tasks to appropriate specialist agents.

**Capabilities**:
- Load agent context and configuration
- Validate task fits agent capabilities
- Execute agents with appropriate CLI
- Validate output against schemas
- Submit results to review cycle

---

### SUPP-05: SpecialistRunner

**Identifier**: `SpecialistRunner`
**File**: `orchestrator/specialists/runner.py`

**Description**: Loads specialist agent configs and executes them.

**Capabilities**:
- Single-shot execution mode
- Iterative (loop) execution mode
- Config loading from agent directories
- Context file reading (CLAUDE.md, GEMINI.md, etc.)

---

## Summary Statistics

| Category | Count |
|----------|-------|
| CLI Agent Wrappers | 4 (including BaseAgent) |
| Specialized Agents | 2 |
| Universal Adapters | 4 (including abstract) |
| Specialist Registry | 15 (A01-A15) |
| LangGraph Nodes | 8 |
| Claude Code Skills | 14 |
| Supporting Components | 5 |
| **Total Agent Definitions** | **52** |

---

## Quick Reference: Agent Selection

| Task Type | Recommended Agent(s) |
|-----------|---------------------|
| Plan feature | A01 (Planner) |
| Write tests | A03 (Test Writer) |
| Implement code | A04 (Implementer), ClaudeAgent |
| Fix bug | A05 (Bug Fixer), FixerAgent |
| Security review | A07 (Security Reviewer), CursorAgent |
| Architecture review | A02 (Architect), GeminiAgent |
| Code review | A08 (Code Reviewer) |
| Refactor | A06 (Refactorer) |
| Write docs | A09 (Documentation Writer) |
| E2E tests | A10 (Integration Tester) |
| CI/CD setup | A11 (DevOps Engineer) |
| UI components | A12 (UI Designer) |

---

## Next Steps: Prompt Optimization

Each agent listed above has prompts that can be optimized. Priority areas:

1. **Specialist Registry (A01-A12)**: Define detailed system prompts
2. **CLI Wrappers**: Optimize prompt templates in `run_*()` methods
3. **LangGraph Nodes**: Review node-specific prompt generation
4. **Skills**: Audit SKILL.md files for clarity and efficiency
