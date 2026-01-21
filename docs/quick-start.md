# Quick Start: Meta-Architect Multi-Agent System

**Date**: January 2026
**For**: AI Coding Agents & Development Teams

---

## Overview

Meta-Architect coordinates **Claude Code, Cursor, and Gemini CLI** through a **5-phase workflow** using LangGraph for orchestration. All agents share context through files in a nested project structure.

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

## Project Structure

Meta-Architect uses a **nested architecture** where projects live in `projects/<name>/`:

```
meta-architect/                    # Orchestrator (outer layer)
├── CLAUDE.md                      # Orchestrator context
├── orchestrator/                  # Python orchestration module
├── scripts/                       # Helper scripts
├── shared-rules/                  # Rules synced to all agents
├── project-templates/             # Templates for new projects
└── projects/                      # Project containers
    └── my-app/                    # Your project (inner layer)
        ├── CLAUDE.md              # Worker Claude context
        ├── GEMINI.md              # Gemini context
        ├── PRODUCT.md             # YOUR FEATURE SPEC
        ├── .cursor/rules          # Cursor rules
        ├── .workflow/             # Workflow state & outputs
        │   ├── state.json
        │   └── phases/
        ├── src/                   # Your application code
        └── tests/                 # Your tests
```

---

## Step 1: Create a Project

```bash
# From meta-architect root directory
./scripts/init.sh create my-app --type node-api

# Available types: node-api, react-tanstack, java-spring, nx-fullstack
```

This creates `projects/my-app/` with all necessary configuration files.

---

## Step 2: Define Your Feature

Edit `projects/my-app/PRODUCT.md` with your feature specification:

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

---

## Step 3: Run the Workflow

```bash
# Start the full 5-phase workflow
./scripts/init.sh run my-app

# Or use the slash command in Claude Code
/orchestrate --project my-app
```

---

## Step 4: Monitor Progress

```bash
# Check workflow status
python -m orchestrator --project my-app --status

# Or use slash command
/phase-status --project my-app

# View detailed dashboard
python -m orchestrator --project my-app --dashboard
```

---

## What Happens in Each Phase

### Phase 1: Planning
Claude reads `PRODUCT.md` and creates:
- `plan.json` - Structured implementation plan
- `PLAN.md` - Human-readable version

### Phase 2: Validation (Parallel)
Cursor and Gemini review the plan simultaneously:
- **Cursor**: Security, code quality, test coverage
- **Gemini**: Architecture, scalability, design patterns

Both must approve (score >= 6.0, no blockers) to proceed.

### Phase 3: Implementation (TDD)
Claude implements using Test-Driven Development:
1. Write failing tests first
2. Implement code to pass tests
3. Refactor while keeping tests green

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
# Create new project
./scripts/init.sh create <name> --type <type>

# List all projects
python -m orchestrator --list-projects

# Sync templates to all projects
python -m orchestrator --sync-projects
```

### Workflow Control

```bash
# Start workflow
python -m orchestrator --project <name> --start

# Resume interrupted workflow
python -m orchestrator --project <name> --resume

# Check status
python -m orchestrator --project <name> --status

# Health check (agent availability)
python -m orchestrator --project <name> --health

# Reset workflow
python -m orchestrator --project <name> --reset
```

### Updates

```bash
# Check for template updates
python -m orchestrator --project <name> --check-updates

# Apply updates (with automatic backup)
python -m orchestrator --project <name> --update

# List backups
python -m orchestrator --project <name> --list-backups

# Rollback to backup
python -m orchestrator --project <name> --rollback-backup <backup-id>
```

---

## Slash Commands (in Claude Code)

| Command | Description |
|---------|-------------|
| `/orchestrate --project <name>` | Start or resume workflow |
| `/phase-status --project <name>` | Show workflow status |
| `/create-project <name>` | Create new project |
| `/list-projects` | List all projects |
| `/check-updates --project <name>` | Check for updates |
| `/update-project --project <name>` | Apply updates |

---

## Configuration Files

### CLAUDE.md (Worker Context)
Instructions for Claude when implementing code in the project.

### GEMINI.md
Instructions for Gemini's architecture reviews.

### .cursor/rules
Rules for Cursor's code quality reviews.

### .project-config.json
Project configuration including:
- Template type
- Version tracking
- Update policy
- Custom settings

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

### Agent Not Available
The workflow can proceed with available agents. Missing agents will be skipped with warnings.

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

1. Create your first project with `./scripts/init.sh create my-app`
2. Write your feature spec in `PRODUCT.md`
3. Run `/orchestrate --project my-app`
4. Watch the agents collaborate through all 5 phases
5. Review the completed implementation

For detailed architecture documentation, see the main [README.md](../README.md).
