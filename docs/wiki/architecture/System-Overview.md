# System Architecture

## 🕸️ LangGraph Orchestration

Conductor uses **LangGraph**, a state-machine library for LLMs, to manage the workflow.

### The Graph Structure

The workflow is defined as a graph of **Nodes** (Units of work) and **Edges** (Decisions).

```python
# Simplified Graph Logic
workflow = StateGraph(WorkflowState)

# Phase 1
workflow.add_node("planning", plan_feature)

# Phase 2 (Parallel)
workflow.add_node("validate_security", run_cursor_security)
workflow.add_node("validate_arch", run_gemini_arch)

# Phase 3 (Loop)
workflow.add_node("implement", run_claude_worker)
workflow.add_node("test", run_tests)

# Define Edges
workflow.add_edge("planning", "validate_security")
workflow.add_edge("planning", "validate_arch")
workflow.add_conditional_edges("test", check_test_results) # -> implement OR verify
```

### State Management (`WorkflowState`)

The state is a strictly typed dictionary that flows through the graph. It is the "memory" of the system.

```python
class WorkflowState(TypedDict):
    project_dir: str
    current_phase: int
    plan: dict                 # Output of Phase 1
    security_feedback: list    # Output of Phase 2/4
    arch_feedback: list        # Output of Phase 2/4
    test_results: dict         # Output of Phase 3
    error_log: list            # Stack traces and recovery attempts
```

---

## 💾 Data Persistence (SurrealDB / SQLite)

We do not rely on in-memory state alone. Every step is **Checkpointed**.

*   **Why?** If the server crashes, or if you stop the script, we can **Resume** exactly where we left off.
*   **Time Travel**: We can "Rewind" the state. If Phase 3 goes wrong, we can revert the state to Phase 2 and try again with a different prompt.

The persistence layer handles:
1.  **Workflow State**: The JSON object above.
2.  **Audit Logs**: Who approved what, and when.
3.  **Metrics**: Token usage, cost, and duration per phase.

---

## 🧩 Modularity & Isolation

### Git Worktrees
To allow agents to work in parallel (e.g., Cursor reviewing while Claude inputs data), we use **Git Worktrees**.
*   Each "Worker" gets its own temporary folder copy of the repo.
*   They communicate via the database/state.
*   They do not lock each other's files.

### File Boundaries
To prevent chaos, we enforce boundaries at the OS level:
*   **Orchestrator** can only write to `.workflow/`.
*   **Workers** can only write to `src/` and `tests/`.
*   **Reviewers** are Read-Only.
