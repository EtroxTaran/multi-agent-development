# Optimization Plan: CLI Agent Distribution & Model Upgrades

**Date:** January 23, 2026
**Target System:** Conductor Multi-Agent Orchestrator

## 1. Executive Summary
This plan addresses the optimization of the "Conductor" system to fully leverage the latest 2026 AI model capabilities across three distinct CLI subscriptions (Claude, Gemini, Cursor). The goal is to standardize model configuration, ensure access to state-of-the-art reasoning, and tighten the feedback loop between "Planner/Implementer" (Claude) and "Reviewers" (Cursor/Gemini).

## 2. Model Upgrades (2026 Standards)

Research confirms the following state-of-the-art models are available as of Jan 2026:

| Agent | Current Config | Target Model (2026) | Role Optimization |
| :--- | :--- | :--- | :--- |
| **Claude** | `sonnet` (Generic) | **`claude-4-5-sonnet`** | **Planner/Coder.** Best balance of reasoning and coding capability. |
| | `opus`, `haiku` | `claude-4-5-opus` | **Deep Reasoning.** Use for initial architectural planning. |
| | | `claude-4-5-haiku` | **Fast Tasks.** Use for simple test generation or small fixes. |
| **Gemini** | `gemini-2.0-flash` | **`gemini-3-flash`** | **Fast Validator.** Quick 1st pass checks on plans. |
| | `gemini-2.0-pro` | **`gemini-3-pro`** | **Architect.** Deep analysis of system design (Phase 2 & 4). |
| **Cursor** | `codex-5.2` | **`gpt-5.2-codex`** | **Code Specialist.** The specific model for `cursor-agent` CLI. |
| | `composer` | **`composer-v2`** | **Agentic Coding.** If available via CLI, for multi-file edits. |

## 3. Implementation Steps

### Phase 1: Centralized Configuration
**Goal:** Eliminate "Configuration Drift" between Python adapters and Shell scripts.

1.  **Create `orchestrator/config/models.py`**
    *   Define constants: `CLAUDE_MODELS`, `GEMINI_MODELS`, `CURSOR_MODELS`.
    *   Define defaults: `DEFAULT_CLAUDE_MODEL`, `DEFAULT_GEMINI_MODEL`, etc.
    *   Map logical names (e.g., "fast", "powerful") to specific model versions.

2.  **Update Python Adapters**
    *   Refactor `orchestrator/agents/adapter.py`, `claude_agent.py`, `gemini_agent.py`, `cursor_agent.py` to import from the new config.
    *   Remove hardcoded model lists in individual files.

3.  **Update Shell Scripts**
    *   Update `scripts/call-gemini.sh` and `scripts/call-cursor.sh` to accept model arguments more flexibly or read from a shared `.env` / config generation step.

### Phase 2: Dynamic Role Dispatch (Future)
**Goal:** Assign the best agent for the specific type of task.

*   **Logic:**
    *   IF `task_type == "architecture"` THEN `reviewer = gemini-3-pro`
    *   IF `task_type == "security"` THEN `reviewer = cursor (gpt-5.2-codex)`
    *   IF `task_type == "optimization"` THEN `reviewer = claude-4-5-opus`

### Phase 3: Enhanced Feedback Injection
**Goal:** Ensure review feedback effectively guides the Planner/Implementer.

1.  **Modify `validation_fan_in_node` (Phase 2)**
    *   Aggregate "Blocking Issues" from Cursor and Gemini.
    *   Format them into a **Structured Correction Prompt**.
    *   *Prompt Template:* "Your previous plan was rejected. You MUST address these specific issues: [List]. Revise the plan accordingly."

2.  **Modify `verification_fan_in_node` (Phase 4)**
    *   Similar logic for code review failures.
    *   Pass specific lint/security errors back to the `fix_bug` node context.

## 4. Verification Plan

1.  **Unit Tests:** Update `tests/test_agent_adapters.py` to verify the new model strings are accepted.
2.  **Integration Test:** Run a "Dry Run" workflow to ensure:
    *   Claude invokes with `claude-4-5-sonnet`.
    *   Gemini invokes `gemini` CLI with `--model gemini-3-pro`.
    *   Cursor invokes `cursor-agent` with correct flags.
3.  **Log Inspection:** Check `logs/` to confirm correct model IDs were logged during execution.
