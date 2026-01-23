"""Mock factory functions for consistent test fixtures.

This module centralizes mock creation to eliminate duplication across test files.
All mock repositories return AsyncMock for async methods.
"""

from unittest.mock import MagicMock, AsyncMock


def create_mock_workflow_state():
    """Create a mock workflow state with all attributes.

    Returns a MagicMock configured with standard workflow state attributes.
    """
    mock_state = MagicMock()
    mock_state.project_dir = "/tmp/test"
    mock_state.project_name = "test_project"  # Fixed: Add project_name
    mock_state.current_phase = 1
    mock_state.phase_status = {}
    mock_state.iteration_count = 0
    mock_state.plan = None
    mock_state.validation_feedback = {}
    mock_state.verification_feedback = {}
    mock_state.implementation_result = None
    mock_state.next_decision = None
    mock_state.execution_mode = "afk"
    mock_state.discussion_complete = False
    mock_state.research_complete = False
    mock_state.research_findings = {}
    mock_state.token_usage = {}
    mock_state.created_at = "2024-01-01T00:00:00"
    mock_state.updated_at = "2024-01-01T00:00:00"
    return mock_state


def create_mock_phase_output_repo():
    """Create a mock PhaseOutputRepository.

    Includes all standard async methods used in phase output operations.
    """
    mock_repo = MagicMock()
    mock_output = MagicMock(id="test-id", content={})

    # Async save methods
    mock_repo.save_output = AsyncMock(return_value=mock_output)
    mock_repo.save_plan = AsyncMock(return_value=mock_output)
    mock_repo.save_cursor_feedback = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_gemini_feedback = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_task_result = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_cursor_review = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_gemini_review = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_summary = AsyncMock(return_value=MagicMock(id="test-id"))

    # Async get methods
    mock_repo.get_output = AsyncMock(return_value=None)
    mock_repo.get_plan = AsyncMock(return_value=None)
    mock_repo.get_task_result = AsyncMock(return_value=None)
    mock_repo.get_phase_outputs = AsyncMock(return_value=[])
    mock_repo.get_task_outputs = AsyncMock(return_value=[])

    # Async utility methods
    mock_repo.clear_phase = AsyncMock(return_value=0)

    return mock_repo


def create_mock_logs_repo():
    """Create a mock LogsRepository.

    Includes all standard async methods used in logging operations.
    """
    mock_repo = MagicMock()
    mock_log = MagicMock(id="test-id", content={})

    # Async save methods
    mock_repo.create_log = AsyncMock(return_value=mock_log)
    mock_repo.save_uat_document = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_handoff_brief = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_discussion = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.save_research = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.log_error = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.log_debug = AsyncMock(return_value=MagicMock(id="test-id"))

    # Async get methods
    mock_repo.get_by_type = AsyncMock(return_value=[])
    mock_repo.get_by_task = AsyncMock(return_value=[])
    mock_repo.get_latest = AsyncMock(return_value=None)
    mock_repo.get_uat_document = AsyncMock(return_value=None)
    mock_repo.get_latest_handoff_brief = AsyncMock(return_value=None)

    # Async utility methods
    mock_repo.clear_by_type = AsyncMock(return_value=0)
    mock_repo.clear_by_task = AsyncMock(return_value=0)

    return mock_repo


def create_mock_workflow_repo():
    """Create a mock WorkflowRepository.

    Includes all standard async methods used in workflow state operations.
    """
    mock_repo = MagicMock()
    mock_state = create_mock_workflow_state()

    # Async state methods
    mock_repo.get_state = AsyncMock(return_value=mock_state)
    mock_repo.initialize_state = AsyncMock(return_value=mock_state)
    mock_repo.update_state = AsyncMock(return_value=mock_state)
    mock_repo.set_phase = AsyncMock(return_value=mock_state)
    mock_repo.reset_state = AsyncMock(return_value=None) # reset_state returns None
    mock_repo.reset_to_phase = AsyncMock(return_value=mock_state)

    # Async summary methods
    mock_repo.get_summary = AsyncMock(return_value={"current_phase": 1, "project": "test"})

    # Async iteration methods
    mock_repo.increment_iteration = AsyncMock(return_value=mock_state)

    # Async setter methods
    mock_repo.set_plan = AsyncMock(return_value=mock_state)
    mock_repo.set_validation_feedback = AsyncMock(return_value=mock_state)
    mock_repo.set_verification_feedback = AsyncMock(return_value=mock_state)
    mock_repo.set_implementation_result = AsyncMock(return_value=mock_state)

    # Async git methods
    mock_repo.record_git_commit = AsyncMock(return_value={})
    mock_repo.get_git_commits = AsyncMock(return_value=[])

    return mock_repo


def create_mock_session_repo():
    """Create a mock SessionRepository.

    Includes all standard async methods used in session management.
    """
    mock_repo = MagicMock()
    mock_session = MagicMock()
    mock_session.task_id = "T1"
    mock_session.session_id = "test-session-id"
    mock_session.agent = "claude"
    mock_session.status = "active"
    mock_session.created_at = None
    mock_session.updated_at = None
    mock_session.invocation_count = 0
    mock_session.total_cost_usd = 0.0

    # Async methods
    mock_repo.create_session = AsyncMock(return_value=mock_session)
    mock_repo.get_session = AsyncMock(return_value=None)
    mock_repo.get_active_session = AsyncMock(return_value=None)
    mock_repo.close_session = AsyncMock(return_value=True)
    mock_repo.close_task_sessions = AsyncMock(return_value=0)
    mock_repo.touch_session = AsyncMock(return_value=mock_session)
    mock_repo.record_invocation = AsyncMock(return_value=mock_session)
    mock_repo.get_task_sessions = AsyncMock(return_value=[])

    return mock_repo


def create_mock_budget_repo():
    """Create a mock BudgetRepository.

    Includes all standard async methods used in budget tracking.
    """
    mock_repo = MagicMock()

    # Async methods
    mock_repo.record_spend = AsyncMock(return_value=MagicMock(id="test-id"))
    mock_repo.get_task_cost = AsyncMock(return_value=0.0)
    mock_repo.get_total_cost = AsyncMock(return_value=0.0)
    mock_repo.get_cost_by_agent = AsyncMock(return_value={})
    mock_repo.get_summary = AsyncMock(
        return_value=MagicMock(
            total_cost_usd=0.0,
            by_agent={},
            by_task={},
            record_count=0,
            total_tokens_input=0,
            total_tokens_output=0,
            by_model={},
        )
    )

    return mock_repo


def create_mock_audit_repo():
    """Create a mock AuditRepository.

    Includes all standard async methods used in audit trail tracking.
    """
    mock_repo = MagicMock()
    mock_entry = MagicMock()
    mock_entry.id = "test-entry-id"

    # Async methods
    mock_repo.create_entry = AsyncMock(return_value=mock_entry)
    mock_repo.update_result = AsyncMock(return_value=mock_entry)
    mock_repo.find_by_task = AsyncMock(return_value=[])
    mock_repo.find_by_agent = AsyncMock(return_value=[])
    mock_repo.find_by_status = AsyncMock(return_value=[])
    mock_repo.find_since = AsyncMock(return_value=[])
    mock_repo.find_all = AsyncMock(return_value=[])
    mock_repo.get_statistics = AsyncMock(
        return_value=MagicMock(
            total=0,
            success_count=0,
            failed_count=0,
            timeout_count=0,
            success_rate=0.0,
            total_cost_usd=0.0,
            total_duration_seconds=0.0,
            avg_duration_seconds=0.0,
            by_agent={},
            by_status={},
        )
    )

    return mock_repo


def create_mock_checkpoint_repo():
    """Create a mock CheckpointRepository.

    Includes all standard async methods used in checkpoint management.
    """
    mock_repo = MagicMock()
    mock_checkpoint = MagicMock()
    mock_checkpoint.id = "test-checkpoint-id"
    mock_checkpoint.name = "test-checkpoint"
    mock_checkpoint.notes = None

    # Async methods
    mock_repo.create = AsyncMock(return_value=mock_checkpoint)
    mock_repo.create_checkpoint = AsyncMock(return_value=mock_checkpoint)
    mock_repo.list_all = AsyncMock(return_value=[])
    mock_repo.list_checkpoints = AsyncMock(return_value=[])
    mock_repo.get_by_id = AsyncMock(return_value=None)
    mock_repo.get_checkpoint = AsyncMock(return_value=None)
    mock_repo.get_latest = AsyncMock(return_value=None)
    mock_repo.delete = AsyncMock(return_value=True)
    mock_repo.delete_checkpoint = AsyncMock(return_value=True)
    mock_repo.prune = AsyncMock(return_value=0)
    mock_repo.prune_old_checkpoints = AsyncMock(return_value=0)

    return mock_repo


def create_mock_task_repo():
    """Create a mock TaskRepository.

    Includes all standard async methods used in task management.
    """
    mock_repo = MagicMock()
    mock_task = MagicMock(id="T1")

    # Async methods
    mock_repo.create_task = AsyncMock(return_value=mock_task)
    mock_repo.get_task = AsyncMock(return_value=None)
    mock_repo.update_task = AsyncMock(return_value=mock_task)
    mock_repo.get_all_tasks = AsyncMock(return_value=[])
    mock_repo.get_pending_tasks = AsyncMock(return_value=[])
    mock_repo.get_next_task = AsyncMock(return_value=None)
    mock_repo.get_progress = AsyncMock(
        return_value=MagicMock(
            total=0,
            completed=0,
            in_progress=0,
            pending=0,
            completion_rate=0.0,
        )
    )

    return mock_repo