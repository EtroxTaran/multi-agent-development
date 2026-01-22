# Documentation Index

**Meta-Architect: Multi-Agent Orchestration System**

This index provides a complete map of all documentation in the project.

---

## Quick Links

| I want to... | Go to |
|--------------|-------|
| **Get started quickly** | [Quick Start Guide](quick-start.md) |
| **Understand everything** | [META-ARCHITECT-GUIDE.md](META-ARCHITECT-GUIDE.md) |
| **See system status** | [SYSTEM-STATUS.md](SYSTEM-STATUS.md) |
| **Learn the architecture** | [SPECIALIST-AGENTS-DESIGN.md](SPECIALIST-AGENTS-DESIGN.md) |
| **Debug an issue** | [Troubleshooting](#troubleshooting) |

---

## Main Documentation (`docs/`)

| Document | Audience | Description |
|----------|----------|-------------|
| [META-ARCHITECT-GUIDE.md](META-ARCHITECT-GUIDE.md) | Everyone | **Comprehensive Wikipedia-style guide** - Start here for complete coverage |
| [quick-start.md](quick-start.md) | Developers | Step-by-step guide to run your first project |
| [SYSTEM-STATUS.md](SYSTEM-STATUS.md) | All | Current status, test coverage, component overview |
| [SPECIALIST-AGENTS-DESIGN.md](SPECIALIST-AGENTS-DESIGN.md) | Technical | 12 specialist agents architecture and design |
| [COMPREHENSIVE-SYSTEM-ANALYSIS.md](COMPREHENSIVE-SYSTEM-ANALYSIS.md) | Technical | Deep technical analysis for AI-assisted review |
| [TASK-LIFECYCLE.md](TASK-LIFECYCLE.md) | Technical | Task state machine and lifecycle |
| [ROUTER-REFERENCE.md](ROUTER-REFERENCE.md) | Technical | Workflow routing and decision logic |

---

## Root-Level Documentation

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Project overview, installation, quick start |
| [CLAUDE.md](../CLAUDE.md) | Orchestrator context (auto-generated from shared-rules) |
| [GEMINI.md](../GEMINI.md) | Gemini context (auto-generated from shared-rules) |
| [.cursor/rules](../.cursor/rules) | Cursor context (auto-generated from shared-rules) |

---

## Shared Rules (`shared-rules/`)

The single source of truth for all agent rules. Run `python scripts/sync-rules.py` to regenerate agent context files.

| File | Description |
|------|-------------|
| [core-rules.md](../shared-rules/core-rules.md) | Fundamental workflow rules (phases, TDD, approvals) |
| [coding-standards.md](../shared-rules/coding-standards.md) | Code patterns, style, conventions |
| [guardrails.md](../shared-rules/guardrails.md) | Safety guardrails (security, boundaries, git) |
| [cli-reference.md](../shared-rules/cli-reference.md) | Correct CLI usage for Claude, Cursor, Gemini |
| [lessons-learned.md](../shared-rules/lessons-learned.md) | Historical fixes and learnings |
| [agent-overrides/claude.md](../shared-rules/agent-overrides/claude.md) | Claude-specific rules |
| [agent-overrides/cursor.md](../shared-rules/agent-overrides/cursor.md) | Cursor-specific rules |
| [agent-overrides/gemini.md](../shared-rules/agent-overrides/gemini.md) | Gemini-specific rules |

---

## Agent Context Files (`agents/`)

Each of the 12 specialist agents has its own context file:

| Agent | Primary CLI | Context File |
|-------|-------------|--------------|
| A01 Planner | Claude | [agents/A01-planner/CLAUDE.md](../agents/A01-planner/CLAUDE.md) |
| A02 Architect | Gemini | [agents/A02-architect/GEMINI.md](../agents/A02-architect/GEMINI.md) |
| A03 Test Writer | Claude | [agents/A03-test-writer/CLAUDE.md](../agents/A03-test-writer/CLAUDE.md) |
| A04 Implementer | Claude | [agents/A04-implementer/CLAUDE.md](../agents/A04-implementer/CLAUDE.md) |
| A05 Bug Fixer | Cursor | [agents/A05-bug-fixer/CURSOR-RULES.md](../agents/A05-bug-fixer/CURSOR-RULES.md) |
| A06 Refactorer | Gemini | [agents/A06-refactorer/GEMINI.md](../agents/A06-refactorer/GEMINI.md) |
| A07 Security Reviewer | Cursor | [agents/A07-security-reviewer/CURSOR-RULES.md](../agents/A07-security-reviewer/CURSOR-RULES.md) |
| A08 Code Reviewer | Gemini | [agents/A08-code-reviewer/GEMINI.md](../agents/A08-code-reviewer/GEMINI.md) |
| A09 Documentation | Claude | [agents/A09-documentation/CLAUDE.md](../agents/A09-documentation/CLAUDE.md) |
| A10 Integration Tester | Claude | [agents/A10-integration-tester/CLAUDE.md](../agents/A10-integration-tester/CLAUDE.md) |
| A11 DevOps | Cursor | [agents/A11-devops/CURSOR-RULES.md](../agents/A11-devops/CURSOR-RULES.md) |
| A12 UI Designer | Claude | [agents/A12-ui-designer/CLAUDE.md](../agents/A12-ui-designer/CLAUDE.md) |

---

## Skills & Commands (`.claude/`)

### Skills (`.claude/skills/`)

Reusable workflow patterns invoked via `/skill-name`:

| Skill | Purpose |
|-------|---------|
| [orchestrate](../.claude/skills/orchestrate/SKILL.md) | Main workflow orchestration |
| [plan-feature](../.claude/skills/plan-feature/SKILL.md) | Planning phase |
| [validate-plan](../.claude/skills/validate-plan/SKILL.md) | Parallel Cursor + Gemini validation |
| [implement-task](../.claude/skills/implement-task/SKILL.md) | TDD implementation |
| [verify-code](../.claude/skills/verify-code/SKILL.md) | Parallel code review |
| [call-cursor](../.claude/skills/call-cursor/SKILL.md) | Cursor agent wrapper |
| [call-gemini](../.claude/skills/call-gemini/SKILL.md) | Gemini agent wrapper |
| [resolve-conflict](../.claude/skills/resolve-conflict/SKILL.md) | Conflict resolution |
| [phase-status](../.claude/skills/phase-status/SKILL.md) | Show workflow status |
| [list-projects](../.claude/skills/list-projects/SKILL.md) | List all projects |
| [sync-rules](../.claude/skills/sync-rules/SKILL.md) | Sync shared rules |
| [add-lesson](../.claude/skills/add-lesson/SKILL.md) | Add lesson learned |

### Commands (`.claude/commands/`)

Slash commands for Claude Code:

| Command | Purpose |
|---------|---------|
| [/orchestrate](../.claude/commands/orchestrate.md) | Start workflow |
| [/validate](../.claude/commands/validate.md) | Run validation phase |
| [/verify](../.claude/commands/verify.md) | Run verification phase |
| [/phase-status](../.claude/commands/phase-status.md) | Show status |
| [/list-projects](../.claude/commands/list-projects.md) | List projects |
| [/resolve-conflict](../.claude/commands/resolve-conflict.md) | Resolve conflicts |
| [/sync-rules](../.claude/commands/sync-rules.md) | Sync rules |
| [/add-lesson](../.claude/commands/add-lesson.md) | Add lesson |

---

## Templates (`templates/`)

| Template | Purpose |
|----------|---------|
| [templates/board/backlog.md](../templates/board/backlog.md) | Kanban backlog template |
| [templates/board/in-progress.md](../templates/board/in-progress.md) | In-progress tasks |
| [templates/board/review.md](../templates/board/review.md) | Tasks in review |
| [templates/board/done.md](../templates/board/done.md) | Completed tasks |
| [templates/board/blocked.md](../templates/board/blocked.md) | Blocked tasks |

---

## Examples (`examples/`)

| Example | Description |
|---------|-------------|
| [jwt-auth-service/PRODUCT.md](../examples/jwt-auth-service/PRODUCT.md) | Example PRODUCT.md for JWT authentication |

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "PRODUCT.md validation failed" | Ensure all required sections, no `[TODO]` placeholders |
| "OrchestratorBoundaryError" | Orchestrator tried to write outside `.workflow/` |
| "WorktreeError: not a git repository" | Initialize git or don't use `--parallel` |
| "Agent failed on both CLIs" | Check `./scripts/init.sh check`, verify rate limits |

### Debug Commands

```bash
# Check prerequisites
./scripts/init.sh check

# View logs
cat projects/<name>/.workflow/coordination.log

# Check escalations
cat projects/<name>/.workflow/escalations/*.json | jq

# Reset and retry
python -m orchestrator --project <name> --reset
```

For detailed troubleshooting, see [META-ARCHITECT-GUIDE.md#16-troubleshooting](META-ARCHITECT-GUIDE.md#16-troubleshooting).

---

## Document Relationships

```
README.md (root)                    <- Entry point, installation
    │
    ├── docs/META-ARCHITECT-GUIDE.md    <- Comprehensive reference
    │       │
    │       ├── docs/quick-start.md         <- Getting started
    │       ├── docs/SYSTEM-STATUS.md       <- Current status
    │       └── docs/SPECIALIST-AGENTS-DESIGN.md <- Agent architecture
    │
    ├── CLAUDE.md (root)                <- Orchestrator context
    │       │
    │       └── shared-rules/*.md           <- Source of truth
    │               │
    │               └── agents/A*/          <- Per-agent context
    │
    └── .claude/skills/*/SKILL.md       <- Workflow skills
```

---

## Contributing to Documentation

1. **Shared rules** → Edit in `shared-rules/`, run `python scripts/sync-rules.py`
2. **Lessons learned** → Add to top of `shared-rules/lessons-learned.md`
3. **Agent context** → Edit in `agents/A*/` for agent-specific rules
4. **Main docs** → Edit directly in `docs/`

---

*Last Updated: 2026-01-22*
