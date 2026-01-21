# CLI Reference (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 2.0 -->
<!-- Last Updated: 2026-01-21 -->

## Correct CLI Usage

This is the authoritative reference for CLI tool invocation. Always use these patterns.

---

## Claude Code CLI

**Command**: `claude`

### Non-Interactive Mode
```bash
claude -p "Your prompt here" --output-format json
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `-p` | Prompt (non-interactive) | `-p "What is 2+2?"` |
| `--output-format` | Output format | `--output-format json` |
| `--allowedTools` | Restrict tools | `--allowedTools "Read,Write,Edit"` |
| `--max-turns` | Limit turns | `--max-turns 10` |

### Full Example
```bash
claude -p "Analyze this code" \
    --output-format json \
    --allowedTools "Read,Grep,Glob" \
    --max-turns 5
```

---

## Cursor Agent CLI

**Command**: `cursor-agent`

### Non-Interactive Mode
```bash
cursor-agent --print --output-format json "Your prompt here"
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--print` or `-p` | Non-interactive mode | `--print` |
| `--output-format` | Output format | `--output-format json` |
| `--force` | Skip confirmations | `--force` |

### Prompt Position
**IMPORTANT**: Prompt is a POSITIONAL argument at the END, not a flag value.

### Full Example
```bash
cursor-agent --print \
    --output-format json \
    --force \
    "Review this code for security issues"
```

### Common Mistakes
- `cursor-agent -p "prompt"` - Wrong! `-p` means `--print`, not prompt
- Prompt must be LAST argument

---

## Gemini CLI

**Command**: `gemini`

### Non-Interactive Mode
```bash
gemini --yolo "Your prompt here"
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--yolo` | Auto-approve tool calls | `--yolo` |
| `--model` | Select model | `--model gemini-2.0-flash` |

### Important Notes
- Gemini does NOT support `--output-format`
- Output must be wrapped in JSON externally if needed
- Prompt is a positional argument

### Full Example
```bash
gemini --model gemini-2.0-flash \
    --yolo \
    "Review architecture of this system"
```

### Common Mistakes
- `gemini --output-format json` - Wrong! Flag doesn't exist
- `gemini -p "prompt"` - Wrong! No `-p` flag

---

## Python Orchestrator

**Command**: `python -m orchestrator`

### Project Management
```bash
# Initialize new project
python -m orchestrator --init-project <name>

# List all projects
python -m orchestrator --list-projects
```

### Workflow Commands (Nested Projects)
```bash
# Start workflow for a nested project
python -m orchestrator --project <name> --start
python -m orchestrator --project <name> --use-langgraph --start

# Resume interrupted workflow
python -m orchestrator --project <name> --resume

# Check status
python -m orchestrator --project <name> --status

# Health check
python -m orchestrator --project <name> --health

# Reset workflow
python -m orchestrator --project <name> --reset

# Rollback to phase
python -m orchestrator --project <name> --rollback 3
```

### Workflow Commands (External Projects)
```bash
# Start workflow for external project
python -m orchestrator --project-path /path/to/project --start
python -m orchestrator --project-path ~/repos/my-app --use-langgraph --start

# Check status
python -m orchestrator --project-path /path/to/project --status
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--project`, `-p` | Project name (nested) | `--project my-app` |
| `--project-path` | External project path | `--project-path ~/repos/my-app` |
| `--start` | Start workflow | `--start` |
| `--resume` | Resume from checkpoint | `--resume` |
| `--status` | Show workflow status | `--status` |
| `--use-langgraph` | Use LangGraph mode | `--use-langgraph` |
| `--health` | Health check | `--health` |
| `--reset` | Reset workflow | `--reset` |
| `--rollback` | Rollback to phase (1-5) | `--rollback 3` |
| `--list-projects` | List all projects | `--list-projects` |
| `--init-project` | Initialize project | `--init-project my-app` |

---

## Shell Script Wrappers

### init.sh - Main Entry Point

```bash
# Check prerequisites
./scripts/init.sh check

# Initialize new project
./scripts/init.sh init <project-name>

# List all projects
./scripts/init.sh list

# Run workflow (nested project)
./scripts/init.sh run <project-name>

# Run workflow (external project)
./scripts/init.sh run --path /path/to/project

# Run with parallel workers (experimental)
./scripts/init.sh run <project-name> --parallel 3

# Check status
./scripts/init.sh status <project-name>

# Show help
./scripts/init.sh help
```

### init.sh Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--path` | External project path | `run --path ~/repos/app` |
| `--parallel` | Parallel workers count | `run my-app --parallel 3` |

### call-cursor.sh
```bash
bash scripts/call-cursor.sh <prompt-file> <output-file> [project-dir]
```

### call-gemini.sh
```bash
bash scripts/call-gemini.sh <prompt-file> <output-file> [project-dir]
```

---

## Environment Variables

### Orchestrator
```bash
# Enable LangGraph mode
export ORCHESTRATOR_USE_LANGGRAPH=true

# Enable Ralph Wiggum loop for TDD
export USE_RALPH_LOOP=auto  # auto | true | false

# Set parallel workers
export PARALLEL_WORKERS=3
```

### Agent CLI Overrides
```bash
export CURSOR_MODEL=gpt-4-turbo      # Override Cursor model
export GEMINI_MODEL=gemini-2.0-flash  # Override Gemini model
```

---

## Quick Reference Table

| Tool | Non-Interactive | Prompt | Output Format |
|------|-----------------|--------|---------------|
| `claude` | `-p "prompt"` | Part of `-p` | `--output-format json` |
| `cursor-agent` | `--print` | Positional (end) | `--output-format json` |
| `gemini` | `--yolo` | Positional | N/A (wrap externally) |

---

## Complete Workflow Examples

### Example 1: New Nested Project
```bash
# 1. Initialize
./scripts/init.sh init my-api

# 2. Add files (manually)
# - projects/my-api/Documents/
# - projects/my-api/PRODUCT.md
# - projects/my-api/CLAUDE.md

# 3. Run workflow
./scripts/init.sh run my-api
```

### Example 2: External Project
```bash
# 1. Ensure project has PRODUCT.md
# 2. Run workflow
./scripts/init.sh run --path ~/repos/existing-project

# Or via Python
python -m orchestrator --project-path ~/repos/existing-project --use-langgraph --start
```

### Example 3: Parallel Implementation
```bash
# Run with 3 parallel workers for independent tasks
./scripts/init.sh run my-app --parallel 3
```

### Example 4: Check and Resume
```bash
# Check status
./scripts/init.sh status my-app

# If paused, resume
python -m orchestrator --project my-app --resume
```
