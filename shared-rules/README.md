# Shared Rules System

This directory contains the **single source of truth** for rules, guardrails, and learned patterns that apply across all CLI agents (Claude, Cursor, Gemini).

## Architecture

```
shared-rules/
├── README.md                    # This file
├── core-rules.md                # Universal rules for ALL agents
├── coding-standards.md          # Shared coding patterns & standards
├── guardrails.md                # Safety & quality guardrails
├── lessons-learned.md           # Bug fixes, mistakes, patterns learned
├── cli-reference.md             # Correct CLI usage for all tools
└── agent-overrides/
    ├── claude.md                # Claude-specific additions
    ├── cursor.md                # Cursor-specific additions
    └── gemini.md                # Gemini-specific additions
```

## How It Works

1. **Shared rules** in this directory are the source of truth
2. **Sync script** compiles shared + agent-specific rules into context files
3. **Agent context files** (CLAUDE.md, GEMINI.md, .cursor/rules) are auto-generated

## Updating Rules

### Add a New Rule for ALL Agents

Edit the appropriate shared file:
- `core-rules.md` - Workflow and behavioral rules
- `coding-standards.md` - Code patterns and conventions
- `guardrails.md` - Safety and quality checks
- `lessons-learned.md` - Bug fixes and learned patterns

Then run:
```bash
python scripts/sync-rules.py
```

### Add a Rule for ONE Agent Only

Edit the agent-specific override file:
- `agent-overrides/claude.md` - Claude only
- `agent-overrides/cursor.md` - Cursor only
- `agent-overrides/gemini.md` - Gemini only

Then run:
```bash
python scripts/sync-rules.py
```

### Record a Lesson Learned

Add to `lessons-learned.md`:
```markdown
### [Date] - Brief Title
- **Issue**: What went wrong
- **Root Cause**: Why it happened
- **Fix**: How it was fixed
- **Prevention**: Rule to prevent recurrence
- **Applies To**: all | claude | cursor | gemini
```

## File Regeneration

The following files are **auto-generated** from shared rules:
- `CLAUDE.md` (project root)
- `GEMINI.md` (project root)
- `.cursor/rules` (project root)

**DO NOT edit these files directly** - edit the shared-rules instead.

## Sync Script Usage

```bash
# Sync all agent files
python scripts/sync-rules.py

# Sync specific agent
python scripts/sync-rules.py --agent claude

# Dry run (show what would change)
python scripts/sync-rules.py --dry-run

# Validate rules (check for conflicts)
python scripts/sync-rules.py --validate
```

## Rule Categories

| Category | File | Description |
|----------|------|-------------|
| Core | `core-rules.md` | Fundamental workflow rules |
| Coding | `coding-standards.md` | Code patterns, style, conventions |
| Safety | `guardrails.md` | Security, quality, error handling |
| Lessons | `lessons-learned.md` | Historical fixes and learnings |
| CLI | `cli-reference.md` | Correct CLI tool usage |
