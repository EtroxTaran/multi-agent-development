"""Planning node for Phase 1.

Generates implementation plan from PRODUCT.md specification
using Claude CLI.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState, PhaseStatus, PhaseState
from ..integrations.action_logging import get_node_logger

logger = logging.getLogger(__name__)

PLANNING_PROMPT = """You are a senior software architect. Analyze the following product specification and create a detailed implementation plan.

PRODUCT SPECIFICATION:
{product_spec}

Create a JSON response with the following structure:
{{
    "plan_name": "Name of the feature/project",
    "summary": "Brief summary of what will be built",
    "phases": [
        {{
            "phase": 1,
            "name": "Phase name",
            "tasks": [
                {{
                    "id": "T1",
                    "description": "Task description",
                    "files": ["list of files to create/modify"],
                    "dependencies": [],
                    "estimated_complexity": "low|medium|high"
                }}
            ]
        }}
    ],
    "test_strategy": {{
        "unit_tests": ["List of unit test files"],
        "integration_tests": ["List of integration tests"],
        "test_commands": ["Commands to run tests"]
    }},
    "risks": ["List of potential risks"],
    "estimated_complexity": "low|medium|high"
}}

Focus on:
1. Breaking work into small, testable tasks
2. Identifying all files that need to be created or modified
3. Defining clear dependencies between tasks
4. Planning tests before implementation (TDD approach)
5. Identifying potential risks and mitigation strategies"""


async def planning_node(state: WorkflowState) -> dict[str, Any]:
    """Generate implementation plan from specification.

    Uses Claude SDK or CLI to analyze PRODUCT.md and generate
    a structured implementation plan.

    Args:
        state: Current workflow state

    Returns:
        State updates with plan or errors
    """
    logger.info(f"Starting planning phase for: {state['project_name']}")

    project_dir = Path(state["project_dir"])
    action_logger = get_node_logger(project_dir)
    start_time = time.time()

    # Log phase start
    action_logger.log_phase_start(1, "Planning")

    # Update phase status
    phase_status = state.get("phase_status", {}).copy()
    phase_1 = phase_status.get("1", PhaseState())
    phase_1.status = PhaseStatus.IN_PROGRESS
    phase_1.started_at = datetime.now().isoformat()
    phase_1.attempts += 1
    phase_status["1"] = phase_1

    # Read PRODUCT.md
    product_file = project_dir / "PRODUCT.md"
    if not product_file.exists():
        action_logger.log_error("PRODUCT.md not found", phase=1)
        return {
            "phase_status": phase_status,
            "errors": [{
                "type": "missing_file",
                "file": "PRODUCT.md",
                "message": "PRODUCT.md not found",
                "phase": 1,
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "abort",
        }

    product_spec = product_file.read_text()

    # Build prompt
    prompt = PLANNING_PROMPT.format(product_spec=product_spec)

    action_logger.log_agent_invoke("claude", "Generating implementation plan", phase=1)

    try:
        # Use Claude CLI to generate plan
        cmd = ["claude", "-p", prompt, "--output-format", "json"]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_dir),
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=300,  # 5 minute timeout
        )

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown error"
            raise Exception(f"Claude CLI failed: {error_msg}")

        output = stdout.decode()

        # Parse the plan from output
        plan = None
        try:
            plan = json.loads(output)
        except json.JSONDecodeError:
            # Try to extract JSON from text
            json_match = re.search(r"\{[\s\S]*\}", output)
            if json_match:
                plan = json.loads(json_match.group(0))
            else:
                raise Exception("Could not parse plan from response")

        # Save plan to file
        plan_dir = project_dir / ".workflow" / "phases" / "planning"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_file = plan_dir / "plan.json"
        plan_file.write_text(json.dumps(plan, indent=2))

        logger.info(f"Plan generated: {plan.get('plan_name', 'Unknown')}")

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Log success
        action_logger.log_agent_complete(
            "claude",
            f"Plan generated: {plan.get('plan_name', 'Unknown')}",
            phase=1,
            duration_ms=duration_ms,
            details={"plan_name": plan.get("plan_name")},
        )
        action_logger.log_phase_complete(1, "Planning", duration_ms=duration_ms)

        # Update phase status
        phase_1.status = PhaseStatus.COMPLETED
        phase_1.completed_at = datetime.now().isoformat()
        phase_1.output = {"plan_file": str(plan_file)}
        phase_status["1"] = phase_1

        return {
            "plan": plan,
            "phase_status": phase_status,
            "current_phase": 2,
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Planning failed: {e}")

        # Log error
        action_logger.log_agent_error("claude", str(e), phase=1, exception=e)

        phase_1.status = PhaseStatus.FAILED
        phase_1.error = str(e)
        phase_status["1"] = phase_1

        # Check if we can retry
        if phase_1.attempts < phase_1.max_attempts:
            action_logger.log_phase_retry(1, phase_1.attempts + 1, phase_1.max_attempts)
            return {
                "phase_status": phase_status,
                "next_decision": "retry",
                "errors": [{
                    "type": "planning_error",
                    "message": str(e),
                    "phase": 1,
                    "attempt": phase_1.attempts,
                    "timestamp": datetime.now().isoformat(),
                }],
            }
        else:
            action_logger.log_phase_failed(1, "Planning", str(e))
            action_logger.log_escalation(f"Planning failed after {phase_1.attempts} attempts", phase=1)
            return {
                "phase_status": phase_status,
                "next_decision": "escalate",
                "errors": [{
                    "type": "planning_error",
                    "message": f"Planning failed after {phase_1.attempts} attempts: {e}",
                    "phase": 1,
                    "timestamp": datetime.now().isoformat(),
                }],
            }
