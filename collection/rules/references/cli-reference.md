---
name: CLI Reference
tags:
  technology: [python]
  feature: [workflow, deployment]
  priority: high
summary: Authoritative CLI reference for Claude, Cursor, Gemini, and Python orchestrator commands
version: 1
---

# CLI Reference

## Quick Reference Table

| Tool | Non-Interactive | Prompt | Output Format |
|------|-----------------|--------|---------------|
| `claude` | `-p "prompt"` | Part of `-p` | `--output-format json` |
| `cursor-agent` | `--print` | Positional (end) | `--output-format json` |
| `gemini` | `--yolo` | Positional | N/A (wrap externally) |

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
| `--permission-mode plan` | Plan before implementing | Tasks touching ≥3 files |
| `--resume <session-id>` | Continue previous session | Loop iterations |
| `--max-budget-usd <n>` | Limit API cost | Always set |

### Full Example
```bash
claude -p "Implement user authentication" \
    --output-format json \
    --permission-mode plan \
    --max-budget-usd 2.00 \
    --allowedTools "Read,Write,Edit,Bash(npm*)" \
    --max-turns 50
```

---

## Cursor Agent CLI

**Command**: `cursor-agent`

### Non-Interactive Mode
```bash
cursor-agent --print --output-format json "Your prompt here"
```

### Key Flags
| Flag | Purpose |
|------|---------|
| `--print` or `-p` | Non-interactive mode |
| `--output-format` | Output format |
| `--force` | Skip confirmations |

**IMPORTANT**: Prompt is a POSITIONAL argument at the END.

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
| Flag | Purpose |
|------|---------|
| `--yolo` | Auto-approve tool calls |
| `--model` | Select model |

**Note**: Gemini does NOT support `--output-format`

---

## Python Orchestrator

**Command**: `python -m orchestrator`

### Project Management
```bash
python -m orchestrator --init-project <name>
python -m orchestrator --list-projects
```

### Workflow Commands
```bash
python -m orchestrator --project <name> --start
python -m orchestrator --project <name> --use-langgraph --start
python -m orchestrator --project <name> --resume
python -m orchestrator --project <name> --status
python -m orchestrator --project-path /path/to/project --start
```

### Key Flags
| Flag | Purpose |
|------|---------|
| `--project`, `-p` | Project name (nested) |
| `--project-path` | External project path |
| `--start` | Start workflow |
| `--resume` | Resume from checkpoint |
| `--status` | Show workflow status |
| `--autonomous` | Run without human input |
| `--use-langgraph` | Use LangGraph mode |

---

## Shell Script Wrappers

### init.sh
```bash
./scripts/init.sh check          # Check prerequisites
./scripts/init.sh init <name>    # Initialize project
./scripts/init.sh list           # List projects
./scripts/init.sh run <name>     # Run workflow
./scripts/init.sh run --path /path/to/project
./scripts/init.sh status <name>  # Check status
```
