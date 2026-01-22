# Plan Feature Skill

Create implementation plans for features using Task tool worker.

## Overview

This skill handles Phase 1 (Planning) of the workflow. It spawns a worker Claude via the Task tool to analyze requirements and create a structured implementation plan.

## Token Efficiency

| Method | Token Cost | Notes |
|--------|-----------|-------|
| Old (subprocess) | ~13k overhead | Full context duplication |
| New (Task tool) | ~4k overhead | Filtered context |
| **Savings** | **70%** | Native integration |

## Input Requirements

Before running this skill, ensure:
- `Docs/PRODUCT.md` exists with feature specification (REQUIRED)
- `Docs/` folder contains project documentation (vision, architecture, requirements)
- `CONTEXT.md` has discussion outcomes (optional)

**Note:** If PRODUCT.md is in project root (legacy), it will be used but a warning is logged. Prefer `Docs/PRODUCT.md`.

## Task Tool Invocation

Use the Task tool with subagent_type="Plan":

```
Task(
  subagent_type="Plan",
  prompt="""
  # Planning Task: Create Implementation Plan

  ## Your Role
  You are a senior software architect creating an implementation plan.

  ## Input Files to Read

  **Step 1: Read ALL documentation from Docs/ folder**

  Use Glob to find all docs:
  ```
  Glob: Docs/**/*.md
  ```

  **Priority order:**
  1. Docs/PRODUCT.md - Feature specification (REQUIRED)
  2. Docs/vision/*.md - Product vision and goals
  3. Docs/architecture/*.md - Technical constraints, design patterns
  4. Docs/requirements/*.md - Functional and non-functional requirements
  5. Docs/decisions/*.md - Architecture decision records (ADRs)

  **Also check:**
  - CONTEXT.md - Developer preferences from discussion (if exists)
  - Existing codebase structure

  **Fallback:** If Docs/PRODUCT.md doesn't exist, check for PRODUCT.md in project root.

  ## Build Context Before Planning

  Before creating the plan, ensure you understand:
  - **Vision**: Why are we building this? (from Docs/vision/)
  - **Constraints**: What technical limitations exist? (from Docs/architecture/)
  - **Requirements**: What must it do? (from Docs/requirements/)
  - **Past decisions**: What has already been decided? (from Docs/decisions/)
  - **Success criteria**: How do we know we're done? (from Docs/PRODUCT.md)

  ## Output Requirements

  Create a plan.json with this structure:
  {
    "feature": {
      "name": "Feature name from PRODUCT.md",
      "summary": "Brief description",
      "acceptance_criteria": ["From PRODUCT.md"]
    },
    "tasks": [
      {
        "id": "T1",
        "title": "Short descriptive title (max 80 chars)",
        "user_story": "As a [user], I want [feature] so that [benefit]",
        "acceptance_criteria": [
          "Criterion 1",
          "Criterion 2"
        ],
        "files_to_create": ["path/to/new/file.py"],
        "files_to_modify": ["path/to/existing/file.py"],
        "test_files": ["tests/test_feature.py"],
        "dependencies": [],
        "priority": "critical|high|medium|low",
        "estimated_complexity": "low|medium|high"
      }
    ],
    "architecture": {
      "patterns": ["Patterns to use"],
      "components": ["Components involved"],
      "data_flow": "Description of data flow"
    },
    "test_strategy": {
      "unit_tests": ["What to unit test"],
      "integration_tests": ["What to integration test"],
      "coverage_target": 80
    },
    "risks": [
      {
        "description": "Risk description",
        "mitigation": "How to mitigate",
        "severity": "high|medium|low"
      }
    ]
  }

  ## Task Granularity Rules

  Each task MUST follow these limits:
  - Max 3 files to create
  - Max 5 files to modify
  - Max 5 acceptance criteria
  - Title max 80 characters
  - Should be completable in <10 minutes

  If a logical task exceeds these limits, SPLIT IT:
  - Group files by directory/module
  - Create T1-a, T1-b, T1-c with dependencies
  - Distribute acceptance criteria

  ## Task Dependencies

  Express dependencies as task IDs:
  - "dependencies": [] = no dependencies, can run first
  - "dependencies": ["T1"] = must run after T1
  - "dependencies": ["T1", "T2"] = must run after both

  ## Priority Guidelines

  - critical: Core functionality, blocks everything
  - high: Important feature, blocks some things
  - medium: Standard feature work
  - low: Nice to have, can be deferred

  ## Output Location

  Save the plan to: .workflow/phases/planning/plan.json

  ## Validation Checklist

  Before completing, verify:
  [ ] All Docs/PRODUCT.md requirements covered
  [ ] All acceptance criteria mapped to tasks
  [ ] Architecture constraints from Docs/architecture/ respected
  [ ] Task dependencies form a valid DAG
  [ ] No circular dependencies
  [ ] Each task respects size limits
  [ ] Test strategy covers all tasks
  [ ] Plan aligns with vision from Docs/vision/
  """,
  run_in_background=false
)
```

## Plan Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["feature", "tasks", "test_strategy"],
  "properties": {
    "feature": {
      "type": "object",
      "required": ["name", "summary"],
      "properties": {
        "name": {"type": "string", "maxLength": 100},
        "summary": {"type": "string", "maxLength": 500},
        "acceptance_criteria": {"type": "array", "items": {"type": "string"}}
      }
    },
    "tasks": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["id", "title", "acceptance_criteria"],
        "properties": {
          "id": {"type": "string", "pattern": "^T\\d+(-[a-z])?$"},
          "title": {"type": "string", "maxLength": 80},
          "user_story": {"type": "string"},
          "acceptance_criteria": {"type": "array", "maxItems": 5},
          "files_to_create": {"type": "array", "maxItems": 3},
          "files_to_modify": {"type": "array", "maxItems": 5},
          "test_files": {"type": "array"},
          "dependencies": {"type": "array", "items": {"type": "string"}},
          "priority": {"enum": ["critical", "high", "medium", "low"]},
          "estimated_complexity": {"enum": ["low", "medium", "high"]}
        }
      }
    },
    "test_strategy": {
      "type": "object",
      "properties": {
        "unit_tests": {"type": "array"},
        "integration_tests": {"type": "array"},
        "coverage_target": {"type": "number", "minimum": 0, "maximum": 100}
      }
    }
  }
}
```

## After Planning

1. **Save plan**: Write to `.workflow/phases/planning/plan.json`

2. **Update state**:
   ```json
   {
     "current_phase": 2,
     "phase_status": {
       "planning": "completed",
       "validation": "in_progress"
     },
     "plan": { ... }
   }
   ```

3. **Proceed to validation**: Run `/validate-plan`

## Auto-Split Logic

If a task exceeds limits, the planning worker should split it:

```
Original Task T1:
  files_to_create: [a.py, b.py, c.py, d.py, e.py, f.py]  # 6 files!

After Auto-Split (max 3):
  T1-a:
    files_to_create: [a.py, b.py, c.py]
    dependencies: []

  T1-b:
    files_to_create: [d.py, e.py, f.py]
    dependencies: ["T1-a"]
```

## Error Handling

### Missing Docs/PRODUCT.md
- Check for PRODUCT.md in project root (legacy fallback)
- If neither exists, cannot proceed without specification
- Ask user to provide Docs/PRODUCT.md or run `/discover`

### Missing Docs/ Folder
- Log warning: "No Docs/ folder found. Planning with limited context."
- Proceed with just PRODUCT.md if available
- Recommend user add supporting documentation

### Task Exceeds Limits
- Auto-split the task
- Log split decision in plan

### Circular Dependencies
- Validate DAG before saving
- Report error if cycles detected

## Related Skills

- `/orchestrate` - Main workflow
- `/validate-plan` - Next phase (validation)
