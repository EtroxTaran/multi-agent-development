# Architecture 2.0 (Jan 2026)

This document describes the architectural improvements introduced in version 2.0 (January 2026), focusing on the Storage Layer decoupling and LangGraph modularization.

## 1. Storage Layer Decoupling

The Orchestrator's storage mechanism has been refactored to use the **Repository Pattern**, decoupling the core logic from specific storage backends (SurrealDB).

### Interface: `StorageRepository`

Defined in `orchestrator/storage/repository.py`, this abstract base class defines the contract for state persistence:

```python
class StorageRepository(ABC):
    @abstractmethod
    def get_state(self) -> Optional[Any]: ...

    @abstractmethod
    def save_state(self, state: Any) -> None: ...

    @abstractmethod
    def get_summary(self) -> dict: ...
```

### Implementation: `SurrealWorkflowRepository`

Located in `orchestrator/storage/surreal_store.py`, this implementation interacts with SurrealDB. It replaces the legacy `WorkflowStorageAdapter` logic, although `WorkflowStorageAdapter` class name is preserved as an alias for backward compatibility.

- **Direct DB Access**: Uses `orchestrator.db.repositories.workflow` for data operations.
- **Async Bridge**: Uses `run_async` to bridge synchronous Orchestrator methods to asynchronous DB calls.

### Usage

The `Orchestrator` is initialized with a `StorageRepository` instance (via dependency injection or factory).

## 2. LangGraph Modularization

The monolithic workflow graph has been split into composable subgraphs to improve maintainability and testability.

### Subgraphs

1.  **`task_subgraph`** (`orchestrator/langgraph/subgraphs/task_graph.py`):
    - Encapsulates the Task Execution Loop: `task_breakdown` -> `select_task` -> `implement_task` -> `verify_task`.
    - Manages task-level state and iteration.

2.  **`fixer_subgraph`** (`orchestrator/langgraph/subgraphs/fixer_graph.py`):
    - Encapsulates Self-Healing logic: `fixer_triage` -> `fixer_diagnose` -> `fixer_validate` -> `fixer_apply` -> `fixer_verify`.
    - Can be invoked from any phase via error dispatch.

### Main Graph Composition

The main `create_workflow_graph` function in `orchestrator/langgraph/workflow.py` now imports and compiles these subgraphs, adding them as nodes in the parent graph.

```python
workflow.add_node("task_loop", task_subgraph)
workflow.add_node("fixer_loop", fixer_subgraph)
```

## 3. Testing Strategy

### Verification

- **`tests/verification/baseline_workflow.py`**: A regression test suite that mocks all agents and generates a deterministic execution trace (`golden_trace.json`) to ensure refactoring doesn't break logic.
- **Storage Tests**: `tests/storage/test_repository_interface.py` ensures compliance with the interface.
- **Mocking**: `tests/conftest.py` uses `auto_patch_db_repos` to prevent accidental DB connections during unit tests.

## 4. Migration Guide

### For Developers

- **State Access**: Do not access `.workflow/state.json` directly. Use `Orchestrator.status()` or `db-cli.py`.
- **Adding Nodes**: If adding a node to the task loop, modify `orchestrator/langgraph/subgraphs/task_graph.py`.
- **DB Changes**: Update `orchestrator/db/models.py` and run migrations.
