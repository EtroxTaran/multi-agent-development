import asyncio
import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch, AsyncMock
from contextlib import ExitStack

from orchestrator.langgraph import WorkflowRunner
from orchestrator.langgraph.state import create_initial_state

# Mock responses for deterministic execution
MOCK_PLAN = {
    "plan_name": "Test Feature",
    "tasks": [
        {
            "id": "T1",
            "title": "Task 1",
            "description": "Do the thing",
            "files": ["test.py"],
            "dependencies": []
        }
    ]
}

MOCK_VALIDATION = {
    "reviewer": "cursor",
    "overall_assessment": "approve",
    "score": 10.0,
    "assessment": "LGTM",
    "concerns": [],
    "blocking_issues": [],
    "summary": "LGTM"
}

MOCK_GEMINI_VALIDATION = {
    "reviewer": "gemini",
    "overall_assessment": "approve",
    "score": 10.0,
    "architecture_review": {
        "concerns": []
    },
    "summary": "LGTM"
}

MOCK_RESEARCH_RESULT = {
    "tech_stack": {"languages": ["python"]},
    "existing_patterns": {"architecture": "clean"}
}

MOCK_IMPLEMENTATION_RESULT = {
    "status": "completed",
    "files_created": ["test.py"],
    "implementation_notes": "Done"
}

class StateTracer:
    def __init__(self):
        self.trace = []

    def on_node_start(self, node_name: str, input_state: dict):
        self._record("start", node_name, input_state)

    def on_node_end(self, node_name: str, output_state: dict):
        self._record("end", node_name, output_state)

    def _record(self, event_type: str, node_name: str, state: dict):
        # Record only deterministic fields to allow comparison
        snapshot = {
            "event": event_type,
            "node": node_name,
            "current_phase": state.get("current_phase"),
            "task_count": len(state.get("tasks", [])),
            "completed_tasks": len(state.get("completed_task_ids", [])),
            "has_plan": state.get("plan") is not None,
            "phase_status": {k: v.status.value if hasattr(v, "status") else v.status for k,v in state.get("phase_status", {}).items()}
        }
        self.trace.append(snapshot)

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.trace, f, indent=2)

async def run_baseline():
    project_dir = Path("tests/verification/project_baseline")
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True)
    
    # Create required files
    (project_dir / "PRODUCT.md").write_text("# Test Product\n\n## Acceptance Criteria\n- [ ] Criteria 1")
    (project_dir / ".project-config.json").write_text("{}")
    (project_dir / "agents" / "A01-planner").mkdir(parents=True)
    (project_dir / "agents" / "A01-planner" / "CLAUDE.md").write_text("Context")

    tracer = StateTracer()
    
    with ExitStack() as stack:
        # Patch Agents & Runners
        MockRunnerPlanning = stack.enter_context(patch("orchestrator.langgraph.nodes.planning.SpecialistRunner"))
        MockCursorAgent = stack.enter_context(patch("orchestrator.agents.CursorAgent"))
        MockSubprocessValidation = stack.enter_context(patch("orchestrator.langgraph.nodes.validation.asyncio.create_subprocess_exec"))
        MockSubprocessResearch = stack.enter_context(patch("orchestrator.langgraph.nodes.research_phase.asyncio.create_subprocess_exec"))
        MockRunnerImpl = stack.enter_context(patch("orchestrator.langgraph.nodes.task.nodes.SpecialistRunner"))
        
        # Patch Configs
        stack.enter_context(patch("orchestrator.langgraph.nodes.task.modes.USE_RALPH_LOOP", "false"))
        stack.enter_context(patch("orchestrator.langgraph.nodes.task.modes.USE_UNIFIED_LOOP_ENV", False))
        
        # Patch Verification
        MockVerifyFiles = stack.enter_context(patch("orchestrator.langgraph.nodes.verify_task._verify_files_created"))
        MockRunTests = stack.enter_context(patch("orchestrator.langgraph.nodes.verify_task._run_task_tests"))
        
        # Patch Repositories
        MockLogsRepo = stack.enter_context(patch("orchestrator.db.repositories.logs.get_logs_repository"))
        MockPhaseRepo = stack.enter_context(patch("orchestrator.db.repositories.phase_outputs.get_phase_output_repository"))
        MockBudget = stack.enter_context(patch("orchestrator.storage.get_budget_storage"))
        
        # Mock run_async at source and in top-level importers
        mock_run_async = MagicMock(return_value=True)
        stack.enter_context(patch("orchestrator.storage.async_utils.run_async", mock_run_async))
        stack.enter_context(patch("orchestrator.storage.surreal_store.run_async", mock_run_async))
        
        # --- Setup Mocks ---
        
        # Repo Mock
        mock_repo = MagicMock()
        mock_repo.create_log = AsyncMock(return_value=True)
        mock_repo.save_plan = AsyncMock(return_value=True)
        mock_repo.save_output = AsyncMock(return_value=True)
        mock_repo.save_cursor_feedback = AsyncMock(return_value=True)
        mock_repo.save_gemini_feedback = AsyncMock(return_value=True)
        
        MockLogsRepo.return_value = mock_repo
        MockPhaseRepo.return_value = mock_repo
        
        MockBudget.return_value = MagicMock(config=MagicMock(enabled=False))

        # Planning
        runner_planning_instance = MockRunnerPlanning.return_value
        agent_planning = MagicMock()
        agent_planning.run.return_value = MagicMock(success=True, output=json.dumps(MOCK_PLAN))
        runner_planning_instance.create_agent.return_value = agent_planning
        
        # Research (Mock subprocess)
        process_mock_research = MagicMock()
        async def async_communicate_research():
            return (json.dumps(MOCK_RESEARCH_RESULT).encode(), b"")
        process_mock_research.communicate.side_effect = async_communicate_research
        process_mock_research.returncode = 0
        
        async def async_subprocess_research(*args, **kwargs):
            return process_mock_research
        MockSubprocessResearch.side_effect = async_subprocess_research

        # Cursor Validation
        cursor_instance = MockCursorAgent.return_value
        cursor_output = {"type": "result", "result": f"```json\n{json.dumps(MOCK_VALIDATION)}\n```"}
        cursor_instance.run.return_value = MagicMock(success=True, parsed_output=cursor_output)
        
        # Gemini Validation
        process_mock_val = MagicMock()
        async def async_communicate_val():
            return (json.dumps(MOCK_GEMINI_VALIDATION).encode(), b"")
        process_mock_val.communicate.side_effect = async_communicate_val
        process_mock_val.returncode = 0
        
        async def async_subprocess_val(*args, **kwargs):
            return process_mock_val
        MockSubprocessValidation.side_effect = async_subprocess_val
        
        # Implementation
        runner_impl_instance = MockRunnerImpl.return_value
        agent_impl = MagicMock()
        agent_impl.run.return_value = MagicMock(success=True, output=json.dumps(MOCK_IMPLEMENTATION_RESULT))
        runner_impl_instance.create_agent.return_value = agent_impl
        
        # Verification
        MockVerifyFiles.return_value = {"success": True}
        MockRunTests.return_value = {"success": True}

        print("Running baseline workflow...")
        
        os.environ["LANGGRAPH_CHECKPOINTER"] = "memory"
        
        runner = WorkflowRunner(project_dir)
        
        async with runner:
            try:
                await runner.run(
                    progress_callback=tracer,
                    config={"execution_mode": "afk"}
                )
            except Exception as e:
                print(f"Workflow stopped with: {e}")
                import traceback
                traceback.print_exc()

    output_path = "tests/verification/golden_trace.json"
    tracer.save(output_path)
    print(f"Golden trace saved to {output_path}")
    
    # Cleanup
    if project_dir.exists():
        shutil.rmtree(project_dir)

if __name__ == "__main__":
    asyncio.run(run_baseline())