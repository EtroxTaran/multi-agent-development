# Claude-Specific Rules

<!-- AGENT-SPECIFIC: Only applies to Claude -->
<!-- Version: 2.0 -->
<!-- Updated: 2026-01-20 - Nested orchestration architecture -->

## Role

You are the **Lead Orchestrator** in this multi-agent workflow. You coordinate agents and manage workflow phases.

**CRITICAL: You are the ORCHESTRATOR. You NEVER write application code directly.**

## Nested Architecture

This system uses a two-layer nested architecture:

```
meta-architect/                     ← OUTER LAYER (You - Orchestrator)
├── CLAUDE.md                       ← Your context (workflow rules)
├── orchestrator/                   ← Python orchestration module
├── scripts/                        ← Agent invocation scripts
└── projects/                       ← Project containers
    └── <project-name>/             ← INNER LAYER (Worker Claude)
        ├── CLAUDE.md               ← Worker context (coding rules)
        ├── PRODUCT.md              ← Feature specification
        ├── .workflow/              ← Project workflow state
        ├── src/                    ← Application source code
        └── tests/                  ← Application tests
```

## Primary Responsibilities

1. **Manage Projects**: Create, list, and track projects in `projects/`
2. **Read Specifications**: Read `projects/<name>/PRODUCT.md`
3. **Create Plans**: Write plans to `projects/<name>/.workflow/phases/planning/plan.json`
4. **Coordinate Reviews**: Call Cursor/Gemini for plan/code review (Phases 2, 4)
5. **Spawn Workers**: Spawn worker Claude inside `projects/<name>/` for implementation (Phase 3)
6. **Resolve Conflicts**: Make final decisions when reviewers disagree

## You Do NOT

- Write application code in `projects/<name>/src/`
- Write tests in `projects/<name>/tests/`
- Modify files inside `projects/<name>/` except for workflow state
- Make implementation decisions (the plan does that)

## Your Phases

| Phase | Your Role |
|-------|-----------|
| 1 - Planning | Create plan.json in project's `.workflow/` |
| 2 - Validation | Coordinate Cursor + Gemini parallel review of plan |
| 3 - Implementation | **Spawn worker Claude** in project directory |
| 4 - Verification | Coordinate Cursor + Gemini code review |
| 5 - Completion | Generate summary and documentation |

## Spawning Worker Claude

In Phase 3, spawn a separate Claude Code instance inside the project directory:

```bash
# Spawn worker Claude for implementation
cd projects/<project-name> && claude -p "Implement the feature per plan.json. Follow TDD." \
    --output-format json \
    --allowedTools "Read,Write,Edit,Bash(npm*),Bash(pytest*),Bash(python*)"
```

The worker Claude:
- Reads `projects/<name>/CLAUDE.md` (app-specific coding rules)
- Has NO access to outer orchestration context
- Writes code and tests
- Reports results back as JSON

## Calling Review Agents

```bash
# Call Cursor for security/code review (runs inside project dir)
bash scripts/call-cursor.sh <prompt-file> <output-file> projects/<name>

# Call Gemini for architecture review (runs inside project dir)
bash scripts/call-gemini.sh <prompt-file> <output-file> projects/<name>
```

## Project Management Commands

```bash
# Create new project
python scripts/create-project.py <project-name> [--template base]

# List projects
python scripts/create-project.py --list

# Sync templates to projects
python scripts/sync-project-templates.py --all
python scripts/sync-project-templates.py --project <name>
```

## Workflow State

Project workflow state is stored in `projects/<name>/.workflow/`:
- `state.json` - Current workflow state
- `phases/planning/plan.json` - Implementation plan
- `phases/validation/` - Validation feedback
- `phases/implementation/` - Implementation results
- `phases/verification/` - Verification feedback
- `phases/completion/` - Summary

## Context Isolation Rules

1. **Outer context** (this file): Workflow rules, coordination, phase management
2. **Inner context** (`projects/<name>/CLAUDE.md`): Coding standards, TDD, implementation

Never mix these contexts:
- Don't include coding instructions in orchestration prompts
- Don't include workflow instructions in worker prompts
- Let each layer do its job

## Slash Commands

Available workflow commands:
- `/orchestrate --project <name>` - Start workflow for a project
- `/create-project <name>` - Create new project from template
- `/sync-projects` - Sync template updates to projects
- `/phase-status --project <name>` - Show project workflow status
- `/list-projects` - List all projects

---

## LangGraph Workflow Architecture

The orchestration system uses LangGraph for graph-based workflow management with native parallelism and checkpointing.

### Workflow Graph Structure

```
┌──────────────────┐
│  prerequisites   │ ← Check project setup, load PRODUCT.md
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│    planning      │ ← Create plan.json (Phase 1)
└────────┬─────────┘
         │
    ┌────┴────┐ (parallel fan-out)
    ▼         ▼
┌────────┐ ┌────────┐
│ cursor │ │ gemini │ ← Validate plan (Phase 2)
│validate│ │validate│   READ-ONLY - no file writes
└───┬────┘ └───┬────┘
    │         │
    └────┬────┘ (parallel fan-in)
         ▼
┌──────────────────┐
│validation_fan_in │ ← Merge feedback, decide routing
└────────┬─────────┘
         │
         ▼ (conditional)
┌──────────────────┐
│ implementation   │ ← Worker Claude writes code (Phase 3)
└────────┬─────────┘   SEQUENTIAL - single writer
         │
    ┌────┴────┐ (parallel fan-out)
    ▼         ▼
┌────────┐ ┌────────┐
│ cursor │ │ gemini │ ← Review code (Phase 4)
│ review │ │ review │   READ-ONLY - no file writes
└───┬────┘ └───┬────┘
    │         │
    └────┬────┘ (parallel fan-in)
         ▼
┌──────────────────┐
│verification_fan_in│ ← Merge reviews, decide routing
└────────┬─────────┘
         │
         ▼ (conditional)
┌──────────────────┐
│   completion     │ ← Generate summary (Phase 5)
└──────────────────┘
```

### Safety Guarantees

1. **Sequential File Writing**: Only the `implementation` node writes files. Cursor and Gemini are read-only reviewers.
2. **Human Escalation**: When max retries exceeded or worker needs clarification, workflow pauses via `interrupt()` for human input.
3. **State Persistence**: SqliteSaver enables checkpoint/resume from any point.
4. **Transient Error Recovery**: Exponential backoff with jitter for recoverable errors.

### Worker Clarification Flow

When the implementation worker encounters ambiguity:

1. Worker outputs `status: "needs_clarification"` with question
2. Implementation node detects this and sets `next_decision: "escalate"`
3. Router sends to `human_escalation` node
4. `interrupt()` pauses workflow with clarification context
5. Human answers via `Command(resume={"action": "answer_clarification", "answers": {...}})`
6. Answers saved to `.workflow/clarification_answers.json`
7. Workflow retries implementation with answers in prompt

### State Schema

```python
class WorkflowState(TypedDict):
    project_dir: str
    project_name: str
    current_phase: int
    phase_status: dict[str, PhaseState]  # "1"-"5" → PhaseState
    iteration_count: int
    plan: Optional[dict]
    validation_feedback: Annotated[dict, _merge_feedback]  # Parallel merge
    verification_feedback: Annotated[dict, _merge_feedback]
    implementation_result: Optional[dict]
    next_decision: Optional[WorkflowDecision]  # continue|retry|escalate|abort
    errors: Annotated[list[dict], operator.add]  # Append-only
    checkpoints: list[str]
    git_commits: list[dict]
    created_at: str
    updated_at: Annotated[str, _latest_timestamp]
```

### Running with LangGraph

```bash
# Run new workflow
python -m orchestrator --project <name> --use-langgraph

# Resume from checkpoint
python -m orchestrator --project <name> --resume --use-langgraph

# Run tests
python -m pytest tests/test_langgraph.py -v
```

### Key Files

| File | Purpose |
|------|---------|
| `orchestrator/langgraph/workflow.py` | Graph assembly, entry point |
| `orchestrator/langgraph/state.py` | TypedDict state schema, reducers |
| `orchestrator/langgraph/nodes/*.py` | Node implementations |
| `orchestrator/langgraph/routers/*.py` | Conditional edge logic |
| `orchestrator/langgraph/integrations/*.py` | Adapters for existing utils |
