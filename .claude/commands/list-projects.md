---
description: List all projects
allowed-tools: ["Bash", "Read"]
---

# List Projects

List all projects in the `projects/` directory.

## Usage

```bash
./scripts/init.sh list
```

Or via Python:

```bash
python -m orchestrator --list-projects
```

## Output

Shows for each project:
- Project name
- Current workflow phase
- Whether Documents/ exists
- Whether context files exist (CLAUDE.md, GEMINI.md, .cursor/rules)

## Example Output

```
Projects:
------------------------------------------------------------
  my-auth-service
    Status: Phase 3, Has docs
    Context: CLAUDE, GEMINI, Cursor
  my-dashboard
    Status: Not started, No docs
    Context: No context files
  api-gateway
    Status: Phase 5, Has docs
    Context: CLAUDE, GEMINI
```

## Related Commands

- `/phase-status --project <name>` - Detailed project status
- `/orchestrate --project <name>` - Start/resume workflow
