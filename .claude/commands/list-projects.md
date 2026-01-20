---
description: List all projects
allowed-tools: ["Bash", "Read"]
---

# List Projects

List all projects in the `projects/` directory.

## Usage

```bash
python -m orchestrator --list-projects
```

Or use the create-project script:

```bash
python scripts/create-project.py --list
```

## Output

Shows for each project:
- Project name
- Template used
- Creation date
- Current workflow phase
- Whether PRODUCT.md exists

## Example Output

```
Projects:
------------------------------------------------------------
  my-auth-service
    Template: base, Status: Phase 3, Has spec
  my-dashboard
    Template: base, Status: Not started, No spec
  api-gateway
    Template: base, Status: Phase 5, Has spec
```

## Related Commands

- `/create-project <name>` - Create a new project
- `/phase-status --project <name>` - Detailed project status
- `/orchestrate --project <name>` - Start/resume workflow
- `/sync-projects` - Sync templates to projects
