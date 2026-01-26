# Rules & Skills Collection

This directory contains the centralized, reusable collection of rules, skills, guardrails, and agent context templates.

## Structure

```
collection/
├── rules/                    # Reusable rules and standards
│   ├── coding-standards/     # Language-specific coding guidelines
│   ├── guardrails/           # Safety and quality guardrails
│   ├── workflows/            # Workflow definitions (TDD, review, etc.)
│   └── references/           # CLI references, API docs, etc.
├── skills/                   # Agent skills (SKILL.md format)
├── templates/                # Agent context templates
│   ├── claude-md/            # CLAUDE.md templates by tech stack
│   └── gemini-md/            # GEMINI.md templates
└── index.json                # Auto-generated manifest (do not edit)
```

## How It Works

1. **Add items** to the appropriate folder with proper YAML frontmatter
2. **Run sync** to update database metadata: `python -m orchestrator.collection sync`
3. **Use in projects** via gap analysis or manual selection

## File Format

All files use YAML frontmatter for metadata:

```markdown
---
name: Python Coding Standards
tags:
  technology: [python, fastapi]
  feature: [backend, api]
  priority: high
summary: Coding standards for Python backend development
version: 1
---

# Content here...
```

## Commands

```bash
# Sync filesystem to database
python -m orchestrator.collection sync

# List all items
python -m orchestrator.collection list

# Run gap analysis for a project
python -m orchestrator.collection gap-analysis <project-name>

# Copy items to project
python -m orchestrator.collection copy <project-name> <item-id> [item-id...]
```

## Tags Reference

### Technology Tags
- `python`, `typescript`, `javascript`, `react`, `nextjs`, `fastapi`, `django`
- `nodejs`, `express`, `surrealdb`, `postgres`, `docker`

### Feature Tags
- `auth`, `api`, `database`, `testing`, `deployment`, `security`
- `frontend`, `backend`, `fullstack`, `websocket`, `realtime`

### Priority Tags
- `critical` - Must have for all projects of this type
- `high` - Strongly recommended
- `medium` - Nice to have
- `low` - Optional enhancement
