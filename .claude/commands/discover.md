---
description: Read Documents/, understand project, create PRODUCT.md
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "TodoWrite", "AskUserQuestion"]
---

# Discovery Phase

Read project documents, build understanding, and create PRODUCT.md.

## Purpose

**Human-guided discovery** - Don't assume, ask questions.

## Workflow

### 1. Find Documents

Look for documentation in:
- `Documents/` folder (primary)
- `docs/` folder (alternative)
- `README.md`
- Any `.md` files in root

List and read all found documents.

### 2. Summarize Understanding

Present what you understand:

```markdown
## What I Understand

### Project Purpose
[Brief summary]

### Current State
[Greenfield or existing code?]

### Feature/Goal
[What we're building]

### Key Constraints
[Technical, timeline, compatibility]
```

### 3. Ask Clarifying Questions

Present 3-5 targeted questions:
- MVP scope vs. nice-to-haves?
- Existing patterns to follow?
- Testing strategy preference?
- Hard deadlines?
- Who reviews before merge?

**Wait for answers before proceeding.**

### 4. Capture Context

Create/update `CONTEXT.md` with:
- Decisions made
- User preferences
- Constraints confirmed
- Out-of-scope items

### 5. Draft PRODUCT.md

Propose a draft with:
- Feature Name
- Summary (50-500 chars)
- Problem Statement (min 100 chars)
- Acceptance Criteria (min 3)
- Example Inputs/Outputs (min 2)
- Technical Constraints
- Testing Strategy
- Definition of Done (min 5 items)

### 6. Get Approval

Ask: "Should I save this as PRODUCT.md?"

Only save after user confirms.

## Key Behaviors

**DO**:
- Read ALL documents before asking questions
- Present understanding for validation
- Ask targeted questions
- Wait for answers
- Be explicit about unknowns

**DON'T**:
- Assume requirements
- Skip to planning
- Create PRODUCT.md without approval
- Rush through discovery

## Transition

When PRODUCT.md created:
```
Discovery complete! PRODUCT.md created.

Next: /plan to create task breakdown
```

## More Details

See full skill documentation: `.claude/skills/discover/SKILL.md`
