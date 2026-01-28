# CLI Reference (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 3.2 -->
<!-- Last Updated: 2026-01-28 -->

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

### Key Flags
| Flag | Purpose |
|------|---------|
| `--print` or `-p` | Non-interactive mode |
| `--output-format` | Output format (json, text) |
| `--mode` | Agent mode (agent, plan, ask) |
| `--resume <thread-id>` | Continue previous session |
| `--model` | Model selection |
| `--force` | Force execution without confirmation |

### Agent Modes (New - Jan 2026)
| Mode | Flag | In-Session | Purpose |
|------|------|------------|---------|
| Agent | `--mode=agent` | (default) | Execute changes directly |
| Plan | `--mode=plan` | `/plan` | Research, ask questions, create plan before coding |
| Ask | `--mode=ask` | `/ask` | Explore code without making changes |

**IMPORTANT: Headless vs Interactive Mode Selection**

| Context | Allowed Modes | Recommended |
|---------|---------------|-------------|
| Orchestrator (headless automation) | `agent`, `ask` | `ask` for analysis |
| Interactive development | All modes | `plan` for complex work |

**Plan mode is INTERACTIVE ONLY** - it requires user input for:
- Clarifying questions
- Plan approval before execution

For headless automation (orchestrator workflow), use:
- `ask` mode for read-only analysis (validation, code review)
- `agent` mode for executing changes

### Plan Mode Workflow (Interactive Only)
1. Agent asks clarifying questions
2. Researches codebase for context
3. Creates implementation plan (markdown file)
4. You review/edit the plan
5. Click "Build" to execute

Plans can be saved to `.cursor/plans/` for team sharing.

### Decision Matrix (Cursor)

| Scenario | Mode | When to Use |
|----------|------|-------------|
| **Orchestrator (Headless)** | | |
| Phase 2 plan validation | ask | Read-only analysis of plan |
| Phase 4 code verification | ask | Read-only code review |
| Routine security scan | agent | Direct execution |
| **Interactive Development** | | |
| Simple code review | agent | Direct validation/verification |
| Complex validation | plan | Multi-file reviews needing context |
| Architecture review | plan | Requires deep codebase research |
| Quick Q&A | ask | Explore without changes |

### Notes
- Prompt is POSITIONAL (at the END)
- Common mistake: `-p "prompt"` is wrong (means `--print`)
- Use `Shift+Tab` to cycle modes in interactive sessions
- `/compress` reduces context window usage

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
- Use Claude plan mode for ≥3 files or high complexity
- Use Cursor plan mode for complex validations requiring deep research
- Resume sessions for Ralph iterations 2+
- Set budget limits on all invocations

**DO NOT without asking:**
- Skip budget limits entirely
- Change project-wide budget limits

### When to Use Cursor Modes

**Headless Automation (Orchestrator):**
- Use `--mode=ask` for analysis (plan validation, code review)
- Use `--mode=agent` (default) for direct execution
- **NEVER use `--mode=plan`** - it requires interactive input

**Interactive Development:**
- Use `--mode=plan` for complex multi-file work
- Use `--mode=ask` for exploration without changes
- Use `--mode=agent` (default) for direct execution

---

**For detailed examples, see `shared-rules/cli-examples.md`.**
