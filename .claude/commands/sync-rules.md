---
description: Sync shared rules to all agent context files
allowed-tools: ["Bash", "Read"]
---

# Sync Shared Rules

Propagate shared rules from `shared-rules/` to all agent context files.

## What Gets Synced

**Source files** (in `shared-rules/`):
- `core-rules.md` - Universal workflow rules
- `coding-standards.md` - Code patterns and conventions
- `guardrails.md` - Safety and quality checks
- `cli-reference.md` - Correct CLI usage
- `lessons-learned.md` - Bug fixes and patterns

**Agent overrides** (in `shared-rules/agent-overrides/`):
- `claude.md` - Claude-specific additions
- `cursor.md` - Cursor-specific additions
- `gemini.md` - Gemini-specific additions

**Target files** (auto-generated):
- `CLAUDE.md` - Claude context
- `GEMINI.md` - Gemini context
- `.cursor/rules` - Cursor rules

## Usage

```bash
# Sync all agents
python scripts/sync-rules.py

# Sync specific agent
python scripts/sync-rules.py --agent claude

# Dry run (show what would change)
python scripts/sync-rules.py --dry-run

# Validate rules
python scripts/sync-rules.py --validate
```

## When to Sync

Run sync after:
- Adding a lesson to `lessons-learned.md`
- Updating any shared rule file
- Modifying agent-specific overrides

## Instructions

1. Run the sync script:
   ```bash
   python scripts/sync-rules.py
   ```

2. Review the output to see which files were updated.

3. If using `--dry-run`, no files are changed - just shows what would happen.
