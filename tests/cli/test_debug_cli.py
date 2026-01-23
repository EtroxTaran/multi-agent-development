"""Tests for Time Travel Debugger CLI."""

import sys
from unittest.mock import MagicMock

# Mock orchestrator module to avoid circular imports and missing dependencies
mock_orchestrator = MagicMock()
sys.modules["orchestrator.orchestrator"] = mock_orchestrator

import pytest
from unittest.mock import patch
from pathlib import Path
from datetime import datetime

from orchestrator.cli.debug import TimeTravelDebugger
from orchestrator.storage.base import CheckpointData

@pytest.fixture
def mock_storage():
    storage = MagicMock()
    # Mock some checkpoints
    storage.list_checkpoints.return_value = [
        CheckpointData(
            id="cp1_hash",
            name="Initial State",
            created_at=datetime.now().isoformat(),
            phase=1,
            state_snapshot={},
            files_snapshot=[]
        ),
        CheckpointData(
            id="cp2_hash",
            name="Pre-Fix",
            created_at=datetime.now().isoformat(),
            phase=2,
            state_snapshot={},
            files_snapshot=[]
        )
    ]
    return storage

def test_list_checkpoints(mock_storage, capsys):
    with patch("orchestrator.cli.debug.get_checkpoint_storage", return_value=mock_storage):
        debugger = TimeTravelDebugger(Path("/tmp"))
        debugger.do_list("")
        
        captured = capsys.readouterr()
        assert "Found 2 checkpoints" in captured.out
        assert "Initial State" in captured.out
        assert "Pre-Fix" in captured.out

def test_checkout_success(mock_storage, capsys):
    mock_storage.rollback_to_checkpoint.return_value = True
    
    with patch("orchestrator.cli.debug.get_checkpoint_storage", return_value=mock_storage):
        with patch("builtins.input", return_value="y"): # Confirm rollback
            debugger = TimeTravelDebugger(Path("/tmp"))
            debugger.do_checkout("cp1") # Partial ID match
            
            captured = capsys.readouterr()
            assert "Rolling back to checkpoint: Initial State" in captured.out
            assert "Rollback successful" in captured.out
            
            mock_storage.rollback_to_checkpoint.assert_called_once()

def test_checkout_ambiguous(mock_storage, capsys):
    # Add ambiguous checkpoint
    checkpoints = mock_storage.list_checkpoints.return_value
    checkpoints.append(CheckpointData(
        id="cp1_dup",
        name="Duplicate Prefix",
        created_at=datetime.now().isoformat(),
        phase=1,
        state_snapshot={},
        files_snapshot=[]
    ))
    
    with patch("orchestrator.cli.debug.get_checkpoint_storage", return_value=mock_storage):
        debugger = TimeTravelDebugger(Path("/tmp"))
        debugger.do_checkout("cp1")
        
        captured = capsys.readouterr()
        assert "Ambiguous ID 'cp1'" in captured.out

def test_replay(mock_storage, capsys):
    with patch("orchestrator.cli.debug.get_checkpoint_storage", return_value=mock_storage):
        debugger = TimeTravelDebugger(Path("/tmp"))
        
        # We need to mock asyncio.run because we are mocking the orchestrator
        with patch("asyncio.run") as mock_run:
            debugger.do_replay("")
            
            captured = capsys.readouterr()
            assert "Resuming workflow..." in captured.out
            assert "Workflow execution finished" in captured.out
            mock_run.assert_called_once()