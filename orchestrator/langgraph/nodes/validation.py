"""Validation nodes for Phase 2.

Cursor and Gemini validate the plan in parallel, then
results are merged in the fan-in node.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState, PhaseStatus, PhaseState, AgentFeedback

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

        # Save feedback
        feedback_dir = project_dir / ".workflow" / "phases" / "validation"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        feedback_file = feedback_dir / "cursor_feedback.json"
        feedback_file.write_text(json.dumps(feedback.to_dict(), indent=2))

        logger.info(f"Cursor validation: {feedback.assessment}, score: {feedback.score}")

        return {
            "validation_feedback": {"cursor": feedback},
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Cursor validation failed: {e}")
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
        # Try SDK first, fall back to CLI
        from ...sdk import AgentFactory, AgentType

        factory = AgentFactory(project_dir=project_dir)
        result = await factory.generate(
            agent_type=AgentType.GEMINI,
            prompt=prompt,
            system_prompt="You are a senior software architect. Always respond with valid JSON.",
            max_tokens=4096,
        )

        if not result.success:
            raise Exception(result.error or "Gemini validation failed")

        # Parse feedback
        feedback_data = result.parsed_output or {}
        if not feedback_data and result.output:
            import re
            json_match = re.search(r"\{[\s\S]*\}", result.output)
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

        # Save feedback
        feedback_dir = project_dir / ".workflow" / "phases" / "validation"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        feedback_file = feedback_dir / "gemini_feedback.json"
        feedback_file.write_text(json.dumps(feedback.to_dict(), indent=2))

        logger.info(f"Gemini validation: {feedback.assessment}, score: {feedback.score}")

        return {
            "validation_feedback": {"gemini": feedback},
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Gemini validation failed: {e}")
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

    # Calculate combined score
    # Weight: Cursor 0.5 for code quality, Gemini 0.5 for architecture
    cursor_score = cursor_feedback.score if hasattr(cursor_feedback, "score") else 0
    gemini_score = gemini_feedback.score if hasattr(gemini_feedback, "score") else 0
    combined_score = (cursor_score * 0.5) + (gemini_score * 0.5)

    # Check for blocking issues
    blocking_issues = []
    if hasattr(cursor_feedback, "blocking_issues"):
        blocking_issues.extend([
            {"agent": "cursor", "issue": issue}
            for issue in cursor_feedback.blocking_issues
        ])
    if hasattr(gemini_feedback, "blocking_issues"):
        blocking_issues.extend([
            {"agent": "gemini", "issue": issue}
            for issue in gemini_feedback.blocking_issues
        ])

    # Determine approval
    cursor_approved = cursor_feedback.approved if hasattr(cursor_feedback, "approved") else False
    gemini_approved = gemini_feedback.approved if hasattr(gemini_feedback, "approved") else False
    both_approved = cursor_approved and gemini_approved

    # Approval thresholds
    MIN_SCORE = 6.0
    approved = both_approved and combined_score >= MIN_SCORE and len(blocking_issues) == 0

    logger.info(
        f"Validation result: score={combined_score:.1f}, "
        f"cursor={cursor_approved}, gemini={gemini_approved}, "
        f"blocking_issues={len(blocking_issues)}, approved={approved}"
    )

    # Save consolidated feedback
    consolidated = {
        "combined_score": combined_score,
        "cursor_approved": cursor_approved,
        "gemini_approved": gemini_approved,
        "approved": approved,
        "blocking_issues": blocking_issues,
        "timestamp": datetime.now().isoformat(),
    }

    feedback_dir = project_dir / ".workflow" / "phases" / "validation"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    (feedback_dir / "consolidated.json").write_text(json.dumps(consolidated, indent=2))

    if approved:
        phase_2.status = PhaseStatus.COMPLETED
        phase_2.completed_at = datetime.now().isoformat()
        phase_status["2"] = phase_2

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
