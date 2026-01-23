"""Tests for LLM diagnosis engine."""

import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.fixer.llm_diagnoser import LLMDiagnosisEngine
from orchestrator.fixer.triage import FixerError, ErrorCategory
from orchestrator.fixer.diagnosis import DiagnosisConfidence, RootCause, AffectedFile

@pytest.fixture
def mock_agent():
    agent = AsyncMock()
    # Mock successful LLM response
    agent.run_iteration.return_value.output = """
```json
{
    "root_cause": "api_misuse",
    "confidence": "high",
    "explanation": "The 'timeout' argument is not supported in this version of the library.",
    "affected_files": [
        {
            "path": "src/api.py",
            "line_number": 42,
            "snippet": "request(timeout=30)",
            "suggested_fix": "Remove timeout arg"
        }
    ],
    "suggested_fixes": ["Remove the timeout argument"]
}
```
"""
    return agent

@pytest.fixture
def diagnosis_engine(tmp_path, mock_agent):
    with patch("orchestrator.fixer.llm_diagnoser.create_adapter", return_value=mock_agent):
        engine = LLMDiagnosisEngine(tmp_path)
        yield engine

def test_diagnose_success(diagnosis_engine, mock_agent):
    error = FixerError(
        error_id="e1",
        error_type="TypeError",
        message="unexpected keyword argument 'timeout'",
        source="execution",
        timestamp="2023-01-01"
    )
    
    async def run_test():
        result = await diagnosis_engine.diagnose(
            error=error,
            category=ErrorCategory.TYPE_ERROR,
            affected_files=[],
            context={}
        )
        
        assert result is not None
        assert result.root_cause == RootCause.API_MISUSE
        assert result.confidence == DiagnosisConfidence.HIGH
        assert len(result.affected_files) == 1
        assert result.affected_files[0].path == "src/api.py"
        
        # Verify prompt contained error info
        call_args = mock_agent.run_iteration.call_args[0][0]
        assert "unexpected keyword argument 'timeout'" in call_args

    asyncio.run(run_test())

def test_diagnose_parsing_failure(diagnosis_engine, mock_agent):
    # Mock bad JSON
    mock_agent.run_iteration.return_value.output = "I think it's a bug but no JSON here."
    
    error = FixerError(
        error_id="e2", 
        error_type="Unknown", 
        message="fail",
        source="test"
    )
    
    async def run_test():
        result = await diagnosis_engine.diagnose(error, ErrorCategory.UNKNOWN, [])
        assert result is None

    asyncio.run(run_test())
