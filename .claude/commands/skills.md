---
description: List all available skills with descriptions
allowed-tools: ["Read", "Glob"]
---

# Available Skills

Display all available skills in the meta-architect system.

## Quick Reference

### Human-Guided Workflow (Recommended)

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/discover` | Read Documents/, understand project, create PRODUCT.md | Starting a new feature |
| `/plan` | Create task breakdown with user approval | After PRODUCT.md exists |
| `/task <id>` | Implement a single task with TDD | During implementation |
| `/status` | Show workflow progress | Anytime |

### Automated Workflow

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/orchestrate` | Run full 5-phase automated workflow | Hands-off execution |

### Agent Invocation

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/validate` | Run Cursor + Gemini validation on plan | Before implementing |
| `/verify` | Run Cursor + Gemini code review | After implementing |
| `/call-cursor` | Direct Cursor agent invocation | Security review |
| `/call-gemini` | Direct Gemini agent invocation | Architecture review |

### Utility

| Command | Description | When to Use |
|---------|-------------|-------------|
| `/skills` | This command - list all skills | Discovering capabilities |
| `/phase-status` | Detailed phase information | Debugging workflow |
| `/resolve-conflict` | Resolve agent disagreements | When reviews conflict |
| `/list-projects` | List available projects | Managing projects |
| `/sync-rules` | Sync shared rules to agents | After rule changes |
| `/add-lesson` | Add a lesson learned | After fixing issues |

## Recommended Workflow Order

```
┌─────────────────────────────────────────────────────────┐
│  1. /discover                                           │
│     └── Read docs, ask questions, create PRODUCT.md     │
│                                                         │
│  2. /plan                                               │
│     └── Create tasks, get approval                      │
│                                                         │
│  3. /task T1 → /task T2 → /task T3...                  │
│     └── Implement each task with TDD                    │
│                                                         │
│  4. /verify (optional)                                  │
│     └── Final code review by Cursor + Gemini            │
│                                                         │
│  5. /status                                             │
│     └── Confirm completion                              │
└─────────────────────────────────────────────────────────┘
```

## Skill Locations

All skills are defined in: `meta-architect/.claude/skills/`

Each skill has:
- `SKILL.md` - Detailed documentation
- Command definition in `.claude/commands/`

## Getting More Help

- For detailed skill docs: Read `meta-architect/.claude/skills/<skill-name>/SKILL.md`
- For workflow overview: See CLAUDE.md
- For quick start: See QUICKSTART.md
