# Cursor Agentic Playbook (Global)

This folder is a **version-controlled source of truth** for:

- A **global “Rules for AI” baseline** (copy/paste into Cursor settings)
- **Cursor Subagent profiles** (copy/symlink to `~/.cursor/agents/`)
- **Workflow macros** (prompt templates) that implement a product→plan→validate→implement→verify loop
- **Global Skills** (optional, nightly channel) under `~/.cursor/skills/`
- **Global Commands** (slash commands) under `~/.cursor/commands/`

## Install (one-time)

### 1) Global Rules

Open Cursor → Settings → **Rules for AI** and paste:

- `global-rules-for-ai.md`

### 2) Subagents (profiles)

Copy the files from `subagents/` into:

- `~/.cursor/agents/`

> Subagents are only available in the **Nightly** update channel per Cursor docs.
> If you don’t see them, switch to Nightly and restart Cursor.

### 3) Skills (global, optional)

Copy the folders from `skills/` into:

- `~/.cursor/skills/`

These are auto-discovered in Cursor Nightly.

### 4) Commands (global, slash commands)

Copy the markdown files from `commands/` into:

- `~/.cursor/commands/`

Then type `/` in chat to use them (e.g. `/orchestrate`, `/plan`, `/verify-code`).

### 3) Perplexity MCP (optional but recommended)

Add the Perplexity MCP server so the agent can do up-to-date research:

- Official Perplexity MCP guide: `https://docs.perplexity.ai/guides/mcp-server`

### 4) Hooks (global)

Hooks allow deterministic safety and quality gates for agent actions:

- Global hooks config: `~/.cursor/hooks.json`
- Hook scripts: `~/.cursor/hooks/`

This playbook installs:
- **beforeShellExecution**: guard dangerous commands; block commits when format/lint/typecheck fail
- **afterFileEdit**: run Prettier (if configured) on edited files
- **MCP + shell audit**: log minimal audit events to `~/.cursor/hooks/logs/agent-audit.jsonl`

See Cursor hooks docs for event semantics:
- `https://cursor.com/docs/agent/hooks#typescript-stop-automation-hook`

## Using the workflow

Start with:

- `workflow/orchestrate.md`

Then the orchestrator will route into:

- `workflow/plan.md`
- `workflow/validate-plan.md`
- `workflow/implement-task.md`
- `workflow/verify-code.md`
- `workflow/resolve-conflict.md`
