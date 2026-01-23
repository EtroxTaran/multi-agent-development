"""Tests for StorageRepository interface compliance."""

import pytest
from orchestrator.storage.repository import StorageRepository
from orchestrator.storage.surreal_store import SurrealWorkflowRepository

def test_surreal_store_implements_interface():
    """Verify SurrealWorkflowRepository implements StorageRepository."""
    assert issubclass(SurrealWorkflowRepository, StorageRepository)
    
    # Check methods exist
    repo = SurrealWorkflowRepository("dummy_path")
    assert hasattr(repo, "get_state")
    assert hasattr(repo, "save_state")
    assert hasattr(repo, "get_summary")
    assert hasattr(repo, "reset_state")
    assert hasattr(repo, "reset_to_phase")
    assert hasattr(repo, "record_git_commit")
    assert hasattr(repo, "get_git_commits")
    
    # Check methods that were part of WorkflowStorageAdapter but maybe not interface
    # These are needed for backward compatibility
    assert hasattr(repo, "initialize_state")
    assert hasattr(repo, "update_state")
    assert hasattr(repo, "set_phase")
    assert hasattr(repo, "increment_iteration")
    assert hasattr(repo, "set_plan")
    assert hasattr(repo, "set_validation_feedback")
    assert hasattr(repo, "set_verification_feedback")
    assert hasattr(repo, "set_implementation_result")
    assert hasattr(repo, "set_decision")
