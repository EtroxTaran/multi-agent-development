"""Validation nodes for Phase 2.

Cursor and Gemini validate the plan in parallel, then
results are merged in the fan-in node.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState, PhaseStatus, PhaseState, AgentFeedback
from ..integrations.action_logging import get_node_logger
from ...review.resolver import ConflictResolver

logger = logging.getLogger(__name__)

CURSOR_VALIDATION_PROMPT = """You are a senior code reviewer validating an implementation plan.

PLAN TO REVIEW:
{plan}

Analyze this plan and provide feedback as JSON:
{{
    "reviewer": "cursor",
    "overall_assessment": "approve|needs_changes|reject",
    "score": 1-10,
    "strengths": [
        "List of plan strengths"
    ],
    "concerns": [
        {{
            "severity": "high|medium|low",
            "area": "Area of concern",
            "description": "Detailed description",
            "suggestion": "How to address it"
        }}
    ],
    "missing_elements": [
        "Any missing elements in the plan"
    ],
    "security_review": {{
        "issues": [],
        "recommendations": []
    }},
    "maintainability_review": {{
        "concerns": [],
        "suggestions": []
    }},
    "summary": "Brief summary of your review"
}}

Focus on:
1. Code quality and best practices
2. Security vulnerabilities
3. Maintainability and readability
4. Test coverage adequacy
5. Error handling completeness"""


GEMINI_VALIDATION_PROMPT = """You are a senior software architect validating an implementation plan.

PLAN TO REVIEW:
{plan}

Analyze this plan from an architectural perspective and provide feedback as JSON:
{{
    "reviewer": "gemini",
    "overall_assessment": "approve|needs_changes|reject",
    "score": 1-10,
    "architecture_review": {{
        "patterns_identified": ["List of design patterns used"],
        "scalability_assessment": "good|adequate|poor",
        "maintainability_assessment": "good|adequate|poor",
        "concerns": [
            {{
                "area": "Area of concern",
                "description": "Detailed description",
                "recommendation": "Suggested improvement"
            }}
        ]
    }},
    "dependency_analysis": {{
        "external_dependencies": ["List of external deps"],
        "internal_dependencies": ["Internal module deps"],
        "potential_conflicts": []
    }},
    "integration_considerations": [
        "Things to consider for integration"
    ],
    "alternative_approaches": [
        {{
            "approach": "Alternative approach name",
            "pros": ["Advantages"],
            "cons": ["Disadvantages"],
            "recommendation": "When to consider this"
        }}
    ],
    "summary": "Brief summary of architectural review"
}}

Focus on:
1. Overall architecture and design patterns
2. Scalability and performance implications
3. Integration with existing systems
4. Long-term maintainability
5. Alternative approaches that might be better"""


async def cursor_validate_node(state: WorkflowState) -> dict[str, Any]:
    """Cursor validates the plan for code quality and security.

    Args:
        state: Current workflow state

    Returns:
        State updates with cursor feedback
    """
    logger.info("Cursor validating plan...")

    project_dir = Path(state["project_dir"])
    action_logger = get_node_logger(project_dir)
    start_time = time.time()

    action_logger.log_agent_invoke("cursor", "Validating plan for code quality", phase=2)

    plan = state.get("plan", {})

    if not plan:
        return {
            "errors": [{
                "type": "validation_error",
                "agent": "cursor",
                "message": "No plan to validate",
                "timestamp": datetime.now().isoformat(),
            }],
        }

    prompt = CURSOR_VALIDATION_PROMPT.format(plan=json.dumps(plan, indent=2))

    try:
        # Cursor is CLI only
        from ...agents import CursorAgent

        agent = CursorAgent(project_dir)
        result = agent.run(prompt)

        if not result.success:
            raise Exception(result.error or "Cursor validation failed")

        # Parse feedback - handle cursor-agent wrapper format
        # cursor-agent returns: {"type":"result","result":"```json\n{...}\n```",...}
        feedback_data = {}
        raw_output = result.parsed_output or {}

        # Check if this is cursor-agent wrapper format
        if isinstance(raw_output, dict) and "result" in raw_output:
            content = raw_output.get("result", "")
            # Extract JSON from markdown code block
            import re
            # Match JSON inside ```json ... ``` or just { ... }
            json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
            if json_match:
                try:
                    feedback_data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            if not feedback_data:
                # Try to find raw JSON
                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    try:
                        feedback_data = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass
        elif isinstance(raw_output, dict) and raw_output.get("reviewer"):
            # Direct feedback format
            feedback_data = raw_output
        elif result.output:
            # Try to extract JSON from raw output
            import re
            json_match = re.search(r"\{[\s\S]*\}", result.output)
            if json_match:
                try:
                    feedback_data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

        feedback = AgentFeedback(
            agent="cursor",
            approved=feedback_data.get("overall_assessment") == "approve",
            score=float(feedback_data.get("score", 0)),
            assessment=feedback_data.get("overall_assessment", "unknown"),
            concerns=feedback_data.get("concerns", []),
            blocking_issues=[
                c["description"] for c in feedback_data.get("concerns", [])
                if c.get("severity") == "high"
            ],
            summary=feedback_data.get("summary", ""),
            raw_output=feedback_data,
        )

        # Save feedback to database
        from ...db.repositories.phase_outputs import get_phase_output_repository
        from ...storage.async_utils import run_async
        repo = get_phase_output_repository(state["project_name"])
        run_async(repo.save_cursor_feedback(feedback.to_dict()))

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"Cursor validation: {feedback.assessment}, score: {feedback.score}")

        # Log validation result
        if feedback.approved:
            action_logger.log_validation_pass("cursor", feedback.score, phase=2)
        else:
            action_logger.log_validation_fail(
                "cursor", feedback.score,
                feedback.summary or "Score below threshold", phase=2
            )

        action_logger.log_agent_complete(
            "cursor",
            f"Validation: {feedback.assessment} (score: {feedback.score:.1f})",
            phase=2,
            duration_ms=duration_ms,
            details={"score": feedback.score, "assessment": feedback.assessment},
        )

        return {
            "validation_feedback": {"cursor": feedback},
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Cursor validation failed: {e}")
        action_logger.log_agent_error("cursor", str(e), phase=2, exception=e)
        return {
            "validation_feedback": {
                "cursor": AgentFeedback(
                    agent="cursor",
                    approved=False,
                    score=0,
                    assessment="error",
                    summary=str(e),
                )
            },
            "errors": [{
                "type": "validation_error",
                "agent": "cursor",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }],
        }


async def gemini_validate_node(state: WorkflowState) -> dict[str, Any]:
    """Gemini validates the plan for architecture.

    Args:
        state: Current workflow state

    Returns:
        State updates with gemini feedback
    """
    logger.info("Gemini validating plan...")

    project_dir = Path(state["project_dir"])
    action_logger = get_node_logger(project_dir)
    start_time = time.time()

    action_logger.log_agent_invoke("gemini", "Validating plan architecture", phase=2)

    plan = state.get("plan", {})

    if not plan:
        return {
            "errors": [{
                "type": "validation_error",
                "agent": "gemini",
                "message": "No plan to validate",
                "timestamp": datetime.now().isoformat(),
            }],
        }

    prompt = GEMINI_VALIDATION_PROMPT.format(plan=json.dumps(plan, indent=2))

    try:
        # Use Gemini CLI to validate plan
        cmd = ["gemini", "--yolo", prompt]

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
            raise Exception(f"Gemini CLI failed: {error_msg}")

        output = stdout.decode()

        # Parse feedback
        feedback_data = {}
        try:
            feedback_data = json.loads(output)
        except json.JSONDecodeError:
            json_match = re.search(r"\{[\s\S]*\}", output)
            if json_match:
                feedback_data = json.loads(json_match.group(0))

        arch_review = feedback_data.get("architecture_review", {})
        concerns = arch_review.get("concerns", [])

        feedback = AgentFeedback(
            agent="gemini",
            approved=feedback_data.get("overall_assessment") == "approve",
            score=float(feedback_data.get("score", 0)),
            assessment=feedback_data.get("overall_assessment", "unknown"),
            concerns=concerns,
            blocking_issues=[
                c["description"] for c in concerns
                if c.get("severity") == "high" or "critical" in c.get("description", "").lower()
            ],
            summary=feedback_data.get("summary", ""),
            raw_output=feedback_data,
        )

        # Save feedback to database
        from ...db.repositories.phase_outputs import get_phase_output_repository
        from ...storage.async_utils import run_async
        repo = get_phase_output_repository(state["project_name"])
        run_async(repo.save_gemini_feedback(feedback.to_dict()))

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"Gemini validation: {feedback.assessment}, score: {feedback.score}")

        # Log validation result
        if feedback.approved:
            action_logger.log_validation_pass("gemini", feedback.score, phase=2)
        else:
            action_logger.log_validation_fail(
                "gemini", feedback.score,
                feedback.summary or "Score below threshold", phase=2
            )

        action_logger.log_agent_complete(
            "gemini",
            f"Validation: {feedback.assessment} (score: {feedback.score:.1f})",
            phase=2,
            duration_ms=duration_ms,
            details={"score": feedback.score, "assessment": feedback.assessment},
        )

        return {
            "validation_feedback": {"gemini": feedback},
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Gemini validation failed: {e}")
        action_logger.log_agent_error("gemini", str(e), phase=2, exception=e)
        return {
            "validation_feedback": {
                "gemini": AgentFeedback(
                    agent="gemini",
                    approved=False,
                    score=0,
                    assessment="error",
                    summary=str(e),
                )
            },
            "errors": [{
                "type": "validation_error",
                "agent": "gemini",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }],
        }


async def validation_fan_in_node(state: WorkflowState) -> dict[str, Any]:
    """Merge validation results and decide next step.

    Combines feedback from Cursor and Gemini, resolves conflicts,
    and determines if the plan can proceed to implementation.

    Args:
        state: Current workflow state with merged validation feedback

    Returns:
        State updates with validation decision
    """
    logger.info("Merging validation results...")

    project_dir = Path(state["project_dir"])
    action_logger = get_node_logger(project_dir)

    action_logger.log_info("Merging validation results", phase=2)

    feedback = state.get("validation_feedback", {})

    cursor_feedback = feedback.get("cursor")
    gemini_feedback = feedback.get("gemini")

    # Update phase status
    phase_status = state.get("phase_status", {}).copy()
    phase_2 = phase_status.get("2", PhaseState())
    phase_2.status = PhaseStatus.IN_PROGRESS
    phase_2.started_at = phase_2.started_at or datetime.now().isoformat()
    phase_2.attempts += 1

    # Check if we have both feedbacks
    if not cursor_feedback or not gemini_feedback:
        missing = []
        if not cursor_feedback:
            missing.append("cursor")
        if not gemini_feedback:
            missing.append("gemini")

        return {
            "phase_status": phase_status,
            "errors": [{
                "type": "validation_incomplete",
                "missing_agents": missing,
                "message": f"Missing feedback from: {', '.join(missing)}",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "retry",
        }

    # Resolve conflicts using 4-Eyes Protocol
    resolver = ConflictResolver()
    result = resolver.resolve(cursor_feedback, gemini_feedback)

    # Determine approval
    approved = result.approved
    combined_score = result.final_score
    blocking_issues = result.blocking_issues

    logger.info(
        f"Validation result: score={combined_score:.1f}, "
        f"approved={approved}, decision={result.action}"
    )

    # Save consolidated feedback
    consolidated = {
        "combined_score": combined_score,
        "cursor_score": cursor_feedback.score if hasattr(cursor_feedback, "score") else 0,
        "gemini_score": gemini_feedback.score if hasattr(gemini_feedback, "score") else 0,
        "approved": approved,
        "decision": result.action,
        "blocking_issues": blocking_issues,
        "timestamp": datetime.now().isoformat(),
    }

    # Save consolidated feedback to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async
    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save(phase=2, output_type="consolidated", content=consolidated))

    if approved:
        phase_2.status = PhaseStatus.COMPLETED
        phase_2.completed_at = datetime.now().isoformat()
        phase_status["2"] = phase_2

        action_logger.log_phase_complete(2, "Validation")
        action_logger.log_info(f"Validation approved with combined score {combined_score:.1f}", phase=2)

        return {
            "phase_status": phase_status,
            "current_phase": 3,
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        # Check if we can retry
        if phase_2.attempts < phase_2.max_attempts:
            # Need to revise plan
            phase_2.blockers = blocking_issues
            phase_status["2"] = phase_2

            action_logger.log_phase_retry(2, phase_2.attempts + 1, phase_2.max_attempts)
            action_logger.log_warning(
                f"Validation needs changes (score: {combined_score:.1f}, blocking issues: {len(blocking_issues)})",
                phase=2
            )

            return {
                "phase_status": phase_status,
                "current_phase": 1,  # Go back to planning
                "next_decision": "retry",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            phase_2.status = PhaseStatus.FAILED
            phase_2.error = f"Validation failed after {phase_2.attempts} attempts"
            phase_status["2"] = phase_2

            action_logger.log_phase_failed(2, "Validation", f"Failed after {phase_2.attempts} attempts")
            action_logger.log_escalation("Validation failed - max retries exceeded", phase=2)

            return {
                "phase_status": phase_status,
                "next_decision": "escalate",
                "errors": [{
                    "type": "validation_failed",
                    "combined_score": combined_score,
                    "blocking_issues": blocking_issues,
                    "message": "Plan validation failed",
                    "timestamp": datetime.now().isoformat(),
                }],
            }
