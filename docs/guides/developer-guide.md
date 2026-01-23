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
