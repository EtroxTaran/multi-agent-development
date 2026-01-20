---
description: Sync templates to projects
allowed-tools: ["Bash", "Read"]
---

# Sync Project Templates

Sync template updates to all projects or a specific project.

## Usage

```bash
# Sync all projects
python scripts/sync-project-templates.py --all

# Sync specific project
python scripts/sync-project-templates.py --project <name>

# Dry run (show what would change)
python scripts/sync-project-templates.py --all --dry-run

# Check sync status
python scripts/sync-project-templates.py --status
```

## What Gets Synced

The following files are regenerated from templates:
- `CLAUDE.md` - Worker Claude context
- `GEMINI.md` - Gemini reviewer context
- `.cursor/rules` - Cursor reviewer context

## Project Overrides

Project-specific rules in `project-overrides/` are preserved and merged:

```
projects/<name>/
├── CLAUDE.md                    # AUTO-GENERATED (template + overrides)
├── project-overrides/
│   └── claude.md                # Project-specific additions (preserved)
```

After sync, `CLAUDE.md` contains:
1. Base template content
2. + Project-specific overrides section

## Template Inheritance

```
project-templates/base/          # Master templates
├── CLAUDE.md.template
├── GEMINI.md.template
└── .cursor/rules.template
         │
         ▼ (sync-project-templates.py)
         │
projects/<name>/                 # Project files
├── CLAUDE.md                    # Generated
├── GEMINI.md                    # Generated
└── .cursor/rules                # Generated
```

## When to Sync

Run sync after:
- Updating templates in `project-templates/`
- Adding new shared rules
- Fixing bugs in template content

## Examples

```bash
# Update templates, then sync all
vim project-templates/base/CLAUDE.md.template
python scripts/sync-project-templates.py --all

# Check which projects need updates
python scripts/sync-project-templates.py --status

# Preview changes before applying
python scripts/sync-project-templates.py --project my-app --dry-run
```

## Notes

- `PRODUCT.md` is NOT synced (it's project-specific)
- Workflow state is NOT affected
- Project overrides are always preserved
- Sync date is tracked in `.project-config.json`
