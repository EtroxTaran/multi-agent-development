# Architectural Overview

## 🏛️ System Philosophy

Conductor is engineered as a **Deterministic Multi-Agent Orchestrator**. Unlike "chatty" autonomous agents that often get stuck in loops, Conductor uses a rigid, state-machine-driven architecture to guarantee progress and quality.

### Core Design Principles

1.  **Orchestration over Autonomy**: Agents do not decide *what* to do next; the **State Machine** (LangGraph) dictates the workflow. Agents only execute the current step.
2.  **Adversarial Validation**: We utilize a **4-Eyes Protocol**. The "Doer" agent (Claude) is never the "Reviewer" agent (Cursor/Gemini). This prevents hallucination propagation.
3.  **State Persistence**: The entire workflow state is serialized to **SurrealDB/SQLite**. This allows for "Time Travel Debugging" (rolling back to a previous state) and crash recovery.
4.  **Test-Driven Sovereignty**: The system treats the *Test Suite* as the ultimate source of truth. Implementation is considered complete *only* when tests pass, not when an LLM says it's done.

---

## 🏗️ High-Level Architecture

The system is composed of three primary layers:

### 1. The Orchestration Layer (Python/LangGraph)
This is the "Brain". It manages the control flow.
*   **Graph Definition**: Uses `langgraph` to define nodes (Planning, Validation, Implementation) and edges (Approvals, Rejections).
*   **State Management**: A typed `WorkflowState` object is passed between nodes, accumulating context, logs, and artifacts.
*   **Dispatch**: Uses `subprocess` calls to invoke the CLI tools of the agents.

### 2. The Agent Layer (CLI Wrappers)
This is the "Muscle". We wrap commercial AI CLI tools to standardize their behavior.
*   **Claude Code (Anthropic)**: The primary "Lead Engineer". High reasoning capability, large context. Used for Planning and complex Implementation.
*   **Cursor (OpenAI Model)**: The "Security Specialist". Excellent at pattern matching and vulnerability scanning.
*   **Gemini (Google)**: The "Architect". Massive context window (1M+ tokens) allows it to read the *entire* codebase to check for architectural consistency.

### 3. The Project Layer (Filesystem)
This is the "Environment".
*   **Isolation**: Each task runs in a strict context. Workers can only modify `src/` and `tests/`.
*   **Configuration**: `PRODUCT.md` serves as the invariant specification.

---

## 🔄 The Cognitive Workflow (5-Phase DAG)

The system implements a Directed Acyclic Graph (DAG) with loops for self-correction:

1.  **Planning (A01)**:
    *   *Input*: `PRODUCT.md`
    *   *Process*: semantic analysis -> dependency mapping -> task breakdown.
    *   *Output*: JSON Execution Plan.
2.  **Validation (Adversarial)**:
    *   *Process*: Parallel execution of A07 (Security) and A02 (Arch).
    *   *Gate*: Weighted scoring algorithm. If score < 6.0, reject to Plan.
3.  **Implementation (TDD Loop)**:
    *   *Process*: `Write Tests (Red)` -> `Write Code (Green)` -> `Refactor`.
    *   *Self-Healing*: If tests fail, `FixerAgent` attempts 3 patches before escalating.
4.  **Verification (Final Gate)**:
    *   *Process*: Parallel full-context review.
    *   *Gate*: Strict compliance check (OWASP Top 10, Style Guide).
5.  **Completion**:
    *   *Process*: Artifact generation, docs update, git commit.

---

## 🧩 Extension Points for Architects

*   **New Agents**: Add to `orchestrator/registry/agents.py`. You can define custom specialized agents (e.g., a "Database Optimizer" agent).
*   **Custom Rules**: Modify `shared-rules/` to enforce organization-wide coding standards (e.g., "Always use TypeScript strict mode").
*   **Integrations**: The `AgentAdapter` class allows you to wrap *any* CLI tool (e.g., a proprietary internal tool) and bring it into the orchestration loop.

---

## 📉 Scalability & Performance

*   **Parallelism**: Independent tasks are executed in parallel using **Git Worktrees** to prevent file locking issues.
*   **Budgeting**: The `BudgetManager` enforces token limits per-step to prevent runaway API costs.
*   **Context Management**: Gemini's high-context window is leveraged to avoid "context stuffing" strategies; we simply feed the whole repo for architectural context.
