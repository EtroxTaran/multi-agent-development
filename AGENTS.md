# Multi-Agent Workflow Rules

<!-- Context Version: 1.0 -->
<!-- Last Updated: Auto-tracked via checksums -->
<!-- This file is tracked for drift detection -->

This project uses a **live multi-agent orchestration system** where Claude Code acts as the orchestrator, coordinating with Cursor and Gemini agents via CLI.

## Architecture Overview

### LangGraph Workflow (Recommended)

The system uses LangGraph for graph-based orchestration with native parallelism and checkpointing:

```
┌──────────────────┐
│  prerequisites   │ ← Check project setup
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│    planning      │ ← Claude creates plan (Phase 1)
└────────┬─────────┘
         │
    ┌────┴────┐ (PARALLEL)
    ▼         ▼
┌────────┐ ┌────────┐
│ Cursor │ │ Gemini │ ← Validate plan (Phase 2)
│validate│ │validate│   READ-ONLY
└───┬────┘ └───┬────┘
    └────┬────┘
         ▼
┌──────────────────┐
│validation_fan_in │ ← Merge feedback
└────────┬─────────┘
         │ (conditional: approve/retry/escalate)
         ▼
┌──────────────────┐
│ implementation   │ ← Worker Claude writes code (Phase 3)
└────────┬─────────┘   SEQUENTIAL (single writer)
         │
    ┌────┴────┐ (PARALLEL)
    ▼         ▼
┌────────┐ ┌────────┐
│ Cursor │ │ Gemini │ ← Review code (Phase 4)
│ review │ │ review │   READ-ONLY
└───┬────┘ └───┬────┘
    └────┬────┘
         ▼
┌──────────────────┐
│verification_fan_in│ ← Merge reviews
└────────┬─────────┘
         │ (conditional: approve/retry/escalate)
         ▼
┌──────────────────┐
│   completion     │ ← Generate summary (Phase 5)
└──────────────────┘
```

**Key Safety Features:**
- **Parallel validation/verification**: Cursor + Gemini run simultaneously (read-only)
- **Sequential implementation**: Single worker writes files (prevents conflicts)
- **Human escalation**: `interrupt()` pauses for human input when needed
- **Checkpoint/resume**: SqliteSaver persists state for recovery

### Legacy CLI Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Code (Orchestrator)                   │
│  - Reads PRODUCT.md                                             │
│  - Creates plans                                                │
│  - Calls other agents via CLI                                   │
│  - Reads JSON responses                                         │
│  - Implements code (TDD)                                        │
│  - Iterates based on feedback                                   │
└─────────────────────────────────────────────────────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────┐              ┌─────────────────────┐
│   Cursor Agent      │              │   Gemini Agent      │
│   (Code Review)     │              │   (Arch Review)     │
│                     │              │                     │
│ - Security analysis │              │ - Design patterns   │
│ - Bug detection     │              │ - Scalability       │
│ - Test coverage     │              │ - System health     │
└─────────────────────┘              └─────────────────────┘
```

## Agent Roles

### Claude Code (Lead Orchestrator)
- **Role**: Planning, implementation, and coordination
- **Phases**: 1 (Planning), 3 (Implementation), 5 (Completion)
- **Responsibilities**:
  - Read PRODUCT.md and understand requirements
  - Create implementation plans
  - Call Cursor/Gemini via bash scripts
  - Parse JSON feedback
  - Iterate on plans based on feedback
  - Implement code using TDD
  - Coordinate all workflow phases

### Cursor Agent (Code Reviewer)
- **Role**: Code quality and security validation
- **Phases**: 2 (Validation), 4 (Verification)
- **Invocation**: `bash scripts/call-cursor.sh <prompt-file> <output-file>`
- **Focus Areas**:
  - Bug detection and prevention
  - Security vulnerability analysis
  - Code style and maintainability
  - Test coverage assessment

### Gemini Agent (Architecture Reviewer)
- **Role**: Architecture and design validation
- **Phases**: 2 (Validation), 4 (Verification)
- **Invocation**: `bash scripts/call-gemini.sh <prompt-file> <output-file>`
- **Focus Areas**:
  - System design and patterns
  - Scalability analysis
  - Integration concerns
  - Performance implications

## Workflow Phases

### Phase 1: Planning (Claude)
Claude reads PRODUCT.md and creates:
- `.workflow/phases/planning/plan.json` (structured)
- `.workflow/phases/planning/PLAN.md` (human-readable)

### Phase 2: Validation (Cursor + Gemini, Parallel)
Claude calls both agents in parallel:
1. Write prompts to `.workflow/phases/validation/`
2. Run bash scripts to invoke agents
3. Read JSON responses
4. Consolidate feedback
5. If changes needed → iterate back to Phase 1

### Phase 3: Implementation (Claude, TDD)
1. Write tests first (expect failures)
2. Implement code
3. Run tests until all pass
4. Update `.workflow/phases/implementation/`

### Phase 4: Verification (Cursor + Gemini, Parallel)
Both agents review the implementation:
1. Cursor: Code quality and security review
2. Gemini: Architecture and design review
3. Both must approve → proceed to Phase 5
4. If changes needed → fix and re-verify

### Phase 5: Completion (Claude)
- Generate summary in `.workflow/phases/completion/`
- Update workflow state
- Report results

## Shared Context Files

| File | Purpose | Read By |
|------|---------|---------|
| `PRODUCT.md` | Feature specification | All agents |
| `AGENTS.md` | This file - workflow rules | All agents |
| `GEMINI.md` | Gemini-specific context | Gemini |
| `.cursor/rules` | Cursor-specific rules | Cursor |
| `.workflow/state.json` | Current workflow state | Claude |

## Directory Structure

```
project/
├── PRODUCT.md              # Feature specification
├── AGENTS.md               # This file
├── GEMINI.md               # Gemini context
├── CLAUDE.md               # Claude context
├── .cursor/
│   └── rules               # Cursor rules
├── .workflow/
│   ├── state.json          # Workflow state
│   └── phases/
│       ├── planning/
│       │   ├── plan.json
│       │   └── PLAN.md
│       ├── validation/
│       │   ├── cursor-prompt.md
│       │   ├── cursor-feedback.json
│       │   ├── gemini-prompt.md
│       │   ├── gemini-feedback.json
│       │   └── consolidated-feedback.md
│       ├── implementation/
│       │   ├── implementation-results.json
│       │   └── test-results.json
│       ├── verification/
│       │   ├── cursor-prompt.md
│       │   ├── cursor-review.json
│       │   ├── gemini-prompt.md
│       │   ├── gemini-review.json
│       │   └── ready-to-merge.json
│       └── completion/
│           ├── completion-summary.json
│           └── COMPLETION.md
```

## JSON Output Schemas

### Plan Schema (Phase 1)
```json
{
  "version": "1.0",
  "feature": "Feature name",
  "summary": "Brief description",
  "components": [
    {
      "name": "ComponentName",
      "type": "file|module|function|class",
      "path": "path/to/file.js",
      "description": "What it does",
      "dependencies": ["other/component"],
      "tests": ["test file paths"]
    }
  ],
  "implementation_order": ["Component1", "Component2"],
  "testing_strategy": {
    "unit_tests": ["description"],
    "integration_tests": ["description"],
    "e2e_tests": ["description"]
  },
  "risks": [
    {
      "description": "Risk description",
      "mitigation": "How to mitigate"
    }
  ]
}
```

### Feedback Schema (Phase 2, 4)
```json
{
  "status": "approved|needs_changes",
  "agent": "cursor|gemini",
  "phase": 2,
  "overall_score": 8,
  "issues": [
    {
      "severity": "critical|major|minor",
      "category": "category name",
      "description": "Issue description",
      "recommendation": "How to fix",
      "affected_component": "Component name"
    }
  ],
  "strengths": ["What's good"],
  "recommendations": ["Suggestions"],
  "approval_conditions": ["If needs_changes, what must be fixed"]
}
```

### State Schema
```json
{
  "current_phase": 1,
  "phase_status": {
    "1": "not_started|in_progress|completed",
    "2": "not_started|in_progress|completed",
    "3": "not_started|in_progress|completed",
    "4": "not_started|in_progress|completed",
    "5": "not_started|in_progress|completed"
  },
  "iteration_count": 0,
  "last_updated": "ISO8601 timestamp",
  "agents_status": {
    "claude": "active|idle",
    "cursor": "pending|completed|error",
    "gemini": "pending|completed|error"
  }
}
```

## Handoff Protocol

### Claude → Cursor/Gemini
1. Write prompt file with context
2. Run bash script
3. Wait for completion
4. Read JSON output file

### Cursor/Gemini → Claude
1. Agent reads context files
2. Agent analyzes plan/code
3. Agent outputs JSON to file
4. Claude reads and processes feedback

## Code Standards

- Follow existing project conventions
- Write tests before implementation (TDD)
- Keep functions small and focused
- Document complex logic
- Handle errors appropriately
- Avoid security vulnerabilities (OWASP Top 10)

## Iteration Rules

- **Max iterations**: 3 per phase (configurable)
- **Escalation**: If max iterations reached, ask human for guidance
- **Approval threshold**: Both agents must approve (or only available agent)
- **Critical issues**: Block progress until resolved

## Approval Policies

| Phase | Policy | Description |
|-------|--------|-------------|
| 2 (Validation) | NO_BLOCKERS | Approve if no blocking issues and score >= 6.0 |
| 4 (Verification) | ALL_MUST_APPROVE | Both agents must approve, score >= 7.0 |

## Conflict Resolution

When agents disagree, resolution uses weighted expertise:

| Area | Cursor Weight | Gemini Weight |
|------|---------------|---------------|
| Security | 0.8 | 0.2 |
| Architecture | 0.3 | 0.7 |
| Code Quality | 0.7 | 0.3 |
| Scalability | 0.2 | 0.8 |
| Testing | 0.7 | 0.3 |

**Strategies**:
- `WEIGHTED`: Prefer agent with higher expertise for the area
- `CONSERVATIVE`: Take the more cautious position
- `ESCALATE`: Require human decision for critical conflicts

## CLI Commands Reference

| CLI | Command | Model | Key Flags |
|-----|---------|-------|-----------|
| Cursor | `cursor-agent -m "$MODEL" -p "prompt"` | GPT-5.2-Codex | `--output-format json`, `--force` |
| Gemini | `gemini -m "$MODEL" -p "prompt"` | Gemini 3 Pro | `--output-format json` |

## Progress Files (Agentic Memory)

To maintain context across long workflows and sessions, agents use progress files:

### Progress File Locations

| File | Purpose | When Updated |
|------|---------|--------------|
| `.workflow/progress/current-task.md` | Active task being worked on | Continuously |
| `.workflow/progress/decisions.md` | Key decisions made and rationale | After major decisions |
| `.workflow/progress/blockers.md` | Issues blocking progress | When blockers arise |
| `.workflow/progress/handoff-notes.md` | Context for session resumption | Before session end |

### Progress File Format

```markdown
# Progress: [Task Name]
## Last Updated: [ISO8601 timestamp]

## Current Status
- Phase: [1-5]
- Step: [Current step description]
- Completion: [X%]

## Recent Actions
1. [Most recent action]
2. [Previous action]

## Pending Items
- [ ] [Next step]
- [ ] [Following step]

## Key Decisions
- **[Decision]**: [Rationale]

## Notes for Resumption
[Context needed to continue work]
```

### Using Progress Files

**Starting a session**:
1. Read `.workflow/progress/handoff-notes.md` (if exists)
2. Read `.workflow/state.json` for workflow state
3. Resume from recorded position

**During work**:
1. Update `current-task.md` at each significant step
2. Record decisions in `decisions.md`
3. Document blockers immediately

**Ending a session**:
1. Write comprehensive `handoff-notes.md`
2. Update `state.json` with latest state
3. Ensure all progress files are current

## Context Checkpointing

### Checkpoint Triggers

| Trigger | Action |
|---------|--------|
| Phase transition | Full state checkpoint |
| Agent feedback received | Feedback checkpoint |
| Implementation milestone | Code checkpoint |
| Error/blocker | Error checkpoint |

### Checkpoint Format

```json
{
  "checkpoint_id": "uuid",
  "timestamp": "ISO8601",
  "phase": 3,
  "trigger": "milestone",
  "state_hash": "sha256",
  "files_changed": ["path/to/file.py"],
  "resumable": true
}
```

## Model Versions (As of January 2026)

| Agent | Default Model | Alternatives | Context Window |
|-------|--------------|--------------|----------------|
| Cursor | GPT-5.2-Codex | gpt-5.1-codex, gpt-4.5-turbo | 256K tokens |
| Gemini | Gemini 3 Pro | gemini-3-flash, gemini-2.5-pro | 1M+ tokens |
| Claude | Claude Opus 4.5 | claude-sonnet-4 | 200K tokens |

### Model Override

```bash
# Environment variables
export CURSOR_MODEL=gpt-5.1-codex
export GEMINI_MODEL=gemini-3-flash
```

---

*This document is read by all agents to ensure consistent workflow execution.*
*Context Version: 2.0 | Models: GPT-5.2-Codex, Gemini 3 Pro*
