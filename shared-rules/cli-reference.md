# CLI Reference (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 3.0 -->
<!-- Last Updated: 2026-01-27 -->

## Quick Reference Table

| Tool | Non-Interactive | Prompt | Output Format |
|------|-----------------|--------|---------------|
| `claude` | `-p "prompt"` | Part of `-p` | `--output-format json` |
| `cursor-agent` | `--print` | Positional (end) | `--output-format json` |
| `gemini` | `--yolo` | Positional | N/A (wrap externally) |

---

## Claude Code CLI

**Command**: `claude -p "prompt" --output-format json`

### Key Flags
| Flag | Purpose |
|------|---------|
| `-p` | Prompt (non-interactive) |
| `--output-format` | Output format (json) |
| `--allowedTools` | Restrict tools |
| `--permission-mode plan` | Plan before implementing |
| `--resume <session-id>` | Continue previous session |
| `--max-budget-usd <n>` | Limit API cost |
| `--fallback-model <model>` | Failover model (sonnet/haiku) |

### Decision Matrix

| Scenario | Plan Mode | Session | Budget |
|----------|-----------|---------|--------|
| Simple 1-2 file task | No | No | $0.50 |
| Multi-file (≥3 files) | Yes | No | $1.00 |
| High complexity | Yes | No | $2.00 |
| Ralph loop iteration 1 | No | New | $0.50 |
| Ralph loop iteration 2+ | No | Resume | $0.50 |

---

## Cursor Agent CLI

**Command**: `cursor-agent --print --output-format json "prompt"`

- `--print` or `-p`: Non-interactive mode
- Prompt is POSITIONAL (at the END)
- Common mistake: `-p "prompt"` is wrong (means `--print`)

---

## Gemini CLI

**Command**: `gemini --yolo "prompt"`

- `--yolo`: Auto-approve tool calls
- `--model`: Select model (gemini-2.0-flash)
- Does NOT support `--output-format`
- Prompt is positional

---

## Python Orchestrator

**Command**: `python -m orchestrator`

### Key Flags
| Flag | Purpose |
|------|---------|
| `--project <name>` | Nested project name |
| `--project-path <path>` | External project path |
| `--start` | Start workflow |
| `--resume` | Resume from checkpoint |
| `--status` | Show workflow status |
| `--autonomous` | Run without human input |

---

## Shell Script (init.sh)

```bash
./scripts/init.sh init <name>     # Initialize project
./scripts/init.sh run <name>      # Run workflow
./scripts/init.sh run --path <p>  # External project
./scripts/init.sh status <name>   # Check status
```

---

## Environment Variables

```bash
export ORCHESTRATOR_USE_LANGGRAPH=true  # LangGraph mode
export USE_RALPH_LOOP=auto              # TDD loop (auto|true|false)
export PARALLEL_WORKERS=3               # Parallel workers
```

---

## Autonomous Decision Guidelines

**DO automatically:**
- Use plan mode for ≥3 files or high complexity
- Resume sessions for Ralph iterations 2+
- Set budget limits on all invocations

**DO NOT without asking:**
- Skip budget limits entirely
- Change project-wide budget limits

---

**For detailed examples, see `shared-rules/cli-examples.md`.**
