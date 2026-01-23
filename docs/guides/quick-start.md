# Quick Start: Conductor Multi-Agent System

**Date**: January 2026
**For**: AI Coding Agents & Development Teams

---

## Overview

Conductor coordinates **Claude Code, Cursor, and Gemini CLI** through a **5-phase workflow** using LangGraph for orchestration. All agents share context through files.

**Two ways to use Conductor:**
1. **Submodule Setup (Recommended)** - Meta-architect as a git submodule in your project
2. **Nested Mode** - Projects inside conductor's `projects/` directory

---

## Submodule Setup (Recommended)

The best way to use conductor is as a **git submodule** in your own project.

### Quick Setup

```bash
# Option A: New project
mkdir my-awesome-app && cd my-awesome-app

# Option B: Existing project
cd /path/to/your/existing-project

# Then run the setup script
curl -sL https://raw.githubusercontent.com/EtroxTaran/multi-agent-development/main/scripts/setup-project.sh | bash
```

### What It Creates

```
my-project/                 <- Run Claude HERE (project root)
├── conductor/         <- Submodule (tools)
├── PRODUCT.md              <- Your feature spec (EDIT THIS)
├── CLAUDE.md               <- Your coding rules
├── run-workflow.sh         <- Convenience script
├── update-conductor.sh <- Update submodule
├── src/                    <- Your code (you create)
└── tests/                  <- Your tests (you create)
```

### Running the Workflow

```bash
cd my-project    # Your project root
claude           # Start Claude here
/orchestrate     # Run the workflow
```

Or use the convenience script:
```bash
./run-workflow.sh
```

### Updating Conductor

```bash
./update-conductor.sh
git commit -m "Update conductor"
```

---

## Workflow Overview

```
PRODUCT.md (Your Feature Spec)
    |
    v
Phase 1: PLANNING (Claude) --> plan.json
    |
    v
Phase 2: VALIDATION (Cursor + Gemini parallel) --> feedback
    |
    v
Phase 3: IMPLEMENTATION (Claude TDD) --> code + tests
    |
    v
Phase 4: VERIFICATION (Cursor + Gemini parallel) --> approvals
    |
    v
Phase 5: COMPLETION --> summary + ready for merge
```

---

## Nested Mode (Alternative)

If you prefer to work within the conductor directory itself, you can use nested mode.

## Project Structure (Nested Mode)

In nested mode, projects live in `projects/<name>/` within conductor:

```
conductor/                    # Orchestrator (outer layer)
├── CLAUDE.md                      # Orchestrator context (auto-generated)
├── orchestrator/                  # Python orchestration module
│   ├── utils/
│   │   ├── boundaries.py          # File boundary enforcement
│   │   └── worktree.py            # Git worktree for parallel workers
│   └── project_manager.py         # Project lifecycle management
├── scripts/                       # Helper scripts
├── shared-rules/                  # Rules synced to all agents
└── projects/                      # Project containers
    └── my-app/                    # Your project (inner layer)
        ├── CLAUDE.md              # Worker Claude context (you provide)
        ├── GEMINI.md              # Gemini context (you provide)
        ├── PRODUCT.md             # YOUR FEATURE SPEC
        ├── .cursor/rules          # Cursor rules (you provide)
        ├── .workflow/             # Workflow state (orchestrator writes here)
        │   ├── state.json
        │   └── phases/
        ├── src/                   # Your application code (workers write here)
        └── tests/                 # Your tests (workers write here)
```

### File Boundary Rules

| Path | Orchestrator | Worker |
|------|--------------|--------|
| `.workflow/**` | **Write** | Read |
| `.project-config.json` | **Write** | Read |
| `src/**` | Read-only | **Write** |
| `tests/**` | Read-only | **Write** |
| `CLAUDE.md` | Read-only | Read |
| `PRODUCT.md` | Read-only | Read |

---

## Step 1: Initialize a Project (Nested Mode)

### Option A: Nested Project (in projects/ directory)

```bash
# From conductor root directory
./scripts/init.sh init my-app
```

This creates `projects/my-app/` with `.workflow/` and `.project-config.json`.

### Option B: External Project (any directory)

```bash
# Point to an existing project
./scripts/init.sh run --path ~/repos/my-existing-project

# Or via Python
python -m orchestrator --project-path ~/repos/my-project --start
```

**Requirements for external projects:**
- Must have `PRODUCT.md` with feature specification
- Should have context files (CLAUDE.md, GEMINI.md, .cursor/rules)
- Should be a git repository (for parallel worker support)

---

## Step 2: Add Your Files

Add these files to your project directory:

### 1. PRODUCT.md (Required)

Your feature specification:

```markdown
# Feature Name
JWT Authentication Service

## Summary
Implement secure JWT-based authentication with login, registration, and token refresh.

## Problem Statement
Users need a secure way to authenticate and maintain sessions without
storing sensitive credentials client-side. Current system lacks proper
authentication, exposing the application to security risks.

## Acceptance Criteria
- [ ] User registration with email validation
- [ ] Login returns JWT access + refresh tokens
- [ ] Token refresh without re-login
- [ ] Tokens expire correctly (15min access, 7day refresh)
- [ ] Rate limiting prevents brute force (max 5 attempts/minute)

## Example Inputs/Outputs

### Registration
```json
// Input
POST /auth/register
{ "email": "user@example.com", "password": "SecurePass123!" }

// Output
{ "success": true, "userId": "uuid-here" }
```

### Login
```json
// Input
POST /auth/login
{ "email": "user@example.com", "password": "SecurePass123!" }

// Output
{ "accessToken": "eyJ...", "refreshToken": "eyJ...", "expiresIn": 900 }
```

## Technical Constraints
- Use bcrypt (cost factor 12) for password hashing
- JWT signed with RS256 algorithm
- Tokens stored in HTTP-only cookies
- Must support Node.js 18+

## Testing Strategy
- Unit tests for all auth functions
- Integration tests for API endpoints
- Security tests for token validation

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Tests passing with 80%+ coverage
- [ ] No high/critical security issues
- [ ] API documentation updated
- [ ] Code reviewed by Cursor and Gemini
```

**Important**: No placeholders like `[TODO]` or `[TBD]` - these will fail validation!

### 2. CLAUDE.md (Recommended)

Context for worker Claude when implementing code. Include:
- Coding standards for your project
- Framework-specific guidelines
- TDD requirements
- Any project-specific rules

### 3. GEMINI.md (Recommended)

Context for Gemini's architecture reviews.

### 4. .cursor/rules (Recommended)

Rules for Cursor's code quality and security reviews.

---

## Step 3: Run the Workflow

### Standard Execution

```bash
# Nested project
./scripts/init.sh run my-app

# External project
./scripts/init.sh run --path ~/repos/my-project

# Or use the slash command in Claude Code
/orchestrate --project my-app
```

### Parallel Workers (Experimental)

For independent tasks, run multiple workers simultaneously:

```bash
# Run with 3 parallel workers using git worktrees
./scripts/init.sh run my-app --parallel 3
```

**Requirements:**
- Project must be a git repository
- Tasks must be independent (no shared file modifications)

---

## Step 4: Monitor Progress

```bash
# Check workflow status
python -m orchestrator --project my-app --status

# Or use slash command
/phase-status --project my-app

# View logs
cat projects/my-app/.workflow/coordination.log
```

---

## What Happens in Each Phase

### Phase 1: Planning
Claude reads `PRODUCT.md` and creates:
- `plan.json` - Structured implementation plan
- Task breakdown with dependencies

### Phase 2: Validation (Parallel)
Cursor and Gemini review the plan simultaneously:
- **Cursor**: Security, code quality, test coverage
- **Gemini**: Architecture, scalability, design patterns

Both must approve (score >= 6.0, no blockers) to proceed.

### Phase 3: Implementation (TDD)
Claude implements using Test-Driven Development:
1. Break feature into tasks
2. For each task:
   - Write failing tests first
   - Implement code to pass tests
   - Verify task completion
3. Verify all tasks complete

### Phase 4: Verification (Parallel)
Cursor and Gemini review the implementation:
- Both must approve (score >= 7.0)
- No blocking security or architecture issues

### Phase 5: Completion
Generate summary and documentation:
- `COMPLETION.md` - Workflow summary
- `metrics.json` - Quality metrics

---

## CLI Commands

### Project Management

```bash
# Initialize new project (nested)
./scripts/init.sh init <name>

# List all projects
./scripts/init.sh list
# or
python -m orchestrator --list-projects
```

### Workflow Control

```bash
# Start workflow (nested)
./scripts/init.sh run <name>
# or
python -m orchestrator --project <name> --start

# Start workflow (external)
./scripts/init.sh run --path /path/to/project
# or
python -m orchestrator --project-path /path/to/project --start

# Parallel workers
./scripts/init.sh run <name> --parallel 3

# Resume interrupted workflow
python -m orchestrator --project <name> --resume

# Check status
./scripts/init.sh status <name>
# or
python -m orchestrator --project <name> --status

# Health check (agent availability)
python -m orchestrator --project <name> --health

# Reset workflow
python -m orchestrator --project <name> --reset

# Rollback to phase
python -m orchestrator --project <name> --rollback 3
```

---

## Slash Commands (in Claude Code)

| Command | Description |
|---------|-------------|
| `/orchestrate --project <name>` | Start or resume workflow |
| `/phase-status --project <name>` | Show workflow status |
| `/list-projects` | List all projects |

---

## Configuration Files

### CLAUDE.md (Worker Context)
Instructions for Claude when implementing code in the project.
**You provide this** - it's specific to your project's coding standards.

### GEMINI.md
Instructions for Gemini's architecture reviews.
**You provide this** - it's specific to your project's architecture.

### .cursor/rules
Rules for Cursor's code quality reviews.
**You provide this** - it's specific to your project's quality standards.

### .project-config.json
Project configuration (auto-created):
- Workflow settings
- Integration configs (e.g., Linear)

Example workflow settings:
```json
{
  "workflow": {
    "parallel_workers": 3,
    "review_gating": "conservative"
  }
}
```
`review_gating` is conservative by default: skip reviews only for docs-only changes.

### .workflow/
Workflow state managed by orchestrator:
- `state.json` - Current workflow state
- `phases/` - Phase-specific outputs

---

## Troubleshooting

### Workflow Not Starting
```bash
# Check prerequisites
python -m orchestrator --project my-app --health
```

### Validation Failing
- Check feedback in `.workflow/phases/validation/`
- Ensure PRODUCT.md has all required sections
- No `[TODO]` or `[TBD]` placeholders
- Minimum score threshold: 6.0

### Agent Not Available
The workflow can proceed with available agents. Missing agents will be skipped with warnings.

### Orchestrator Boundary Error
```
OrchestratorBoundaryError: Orchestrator cannot write to 'src/main.py'.
```
The orchestrator tried to write to application code. This is blocked by design.
Solution: Ensure workers handle code changes, not the orchestrator.

### Worktree Error
```
WorktreeError: '/path/to/project' is not a git repository.
```
Parallel workers require git. Initialize a git repo or don't use `--parallel`.

### Context Issues
```bash
# View logs
cat projects/my-app/.workflow/coordination.log

# Reset and restart
python -m orchestrator --project my-app --reset
python -m orchestrator --project my-app --start
```

---

## Next Steps

1. Initialize your project with `./scripts/init.sh init my-app`
2. Add your context files (CLAUDE.md, GEMINI.md, .cursor/rules)
3. Write your feature spec in `PRODUCT.md`
4. Run `/orchestrate --project my-app`
5. Watch the agents collaborate through all 5 phases
6. Review the completed implementation

For detailed architecture documentation, see:
- [CLAUDE.md](../CLAUDE.md) - Full orchestrator documentation
- [shared-rules/](../shared-rules/) - Agent rules and guardrails
- [README.md](../README.md) - System overview
