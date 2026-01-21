"""Verification nodes for Phase 4.

Cursor reviews code quality and Gemini reviews architecture,
then results are merged to determine approval.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from ..state import WorkflowState, PhaseStatus, PhaseState, AgentFeedback

logger = logging.getLogger(__name__)

CURSOR_REVIEW_PROMPT = """You are a senior code reviewer performing a detailed code review.

ORIGINAL PLAN:
{plan}

FILES IMPLEMENTED:
{files_list}

Review each file and provide feedback as JSON:
{{
    "reviewer": "cursor",
    "approved": true|false,
    "review_type": "code_review",
    "files_reviewed": [
        {{
            "file": "path/to/file",
            "status": "approved|needs_changes",
            "issues": [
                {{
                    "line": 42,
                    "severity": "error|warning|info",
                    "type": "bug|security|style|performance",
                    "description": "Issue description",
                    "suggestion": "How to fix"
                }}
            ],
            "positive_feedback": ["Good practices observed"]
        }}
    ],
    "overall_code_quality": 1-10,
    "test_coverage_assessment": "adequate|insufficient|excellent",
    "security_assessment": "pass|fail|needs_review",
    "blocking_issues": [
        "List of issues that must be fixed before merge"
    ],
    "summary": "Overall review summary"
}}

Focus on:
1. Code correctness and bug detection
2. Security vulnerabilities (OWASP Top 10)
3. Performance issues
4. Code style and consistency
5. Test quality and coverage"""


GEMINI_REVIEW_PROMPT = """You are a senior software architect reviewing an implementation.

ORIGINAL PLAN:
{plan}

FILES IMPLEMENTED:
{files_list}

Review the implementation from an architectural perspective and provide feedback as JSON:
{{
    "reviewer": "gemini",
    "approved": true|false,
    "review_type": "architecture_review",
    "plan_adherence": {{
        "followed_plan": true|false,
        "deviations": [
            {{
                "planned": "What was planned",
                "actual": "What was implemented",
                "acceptable": true|false,
                "reason": "Why deviation occurred"
            }}
        ]
    }},
    "architecture_assessment": {{
        "patterns_used": ["Design patterns identified in code"],
        "modularity_score": 1-10,
        "coupling_assessment": "loose|moderate|tight",
        "cohesion_assessment": "high|moderate|low",
        "concerns": []
    }},
    "scalability_assessment": {{
        "current_capacity": "Assessment of current design",
        "bottlenecks": ["Potential bottlenecks"],
        "recommendations": ["Scaling recommendations"]
    }},
    "technical_debt": {{
        "items": [
            {{
                "description": "Technical debt item",
                "severity": "high|medium|low",
                "recommendation": "How to address"
            }}
        ],
        "overall_health": "good|acceptable|concerning"
    }},
    "blocking_issues": [
        "Architectural issues that must be addressed"
    ],
    "summary": "Overall architecture review summary"
}}

Focus on:
1. Adherence to the original plan
2. Code organization and modularity
3. Design pattern usage
4. Scalability potential
5. Technical debt introduced"""


async def cursor_review_node(state: WorkflowState) -> dict[str, Any]:
    """Cursor reviews the implementation for code quality.

    Args:
        state: Current workflow state

    Returns:
        State updates with cursor review feedback
    """
    logger.info("Cursor reviewing implementation...")

    project_dir = Path(state["project_dir"])
    plan = state.get("plan", {})
    impl_result = state.get("implementation_result", {})

    # Get list of changed files
    files_changed = []
    if impl_result:
        files_changed.extend(impl_result.get("files_created", []))
        files_changed.extend(impl_result.get("files_modified", []))

    if not files_changed:
        # Try to get from git
        files_changed = await _get_changed_files(project_dir)

    files_list = "\n".join(f"- {f}" for f in files_changed) if files_changed else "No files specified"

    prompt = CURSOR_REVIEW_PROMPT.format(
        plan=json.dumps(plan, indent=2),
        files_list=files_list,
    )

    try:
        from ...agents import CursorAgent

        agent = CursorAgent(project_dir)
        result = agent.run(prompt)

        if not result.success:
            raise Exception(result.error or "Cursor review failed")

        # Parse feedback - handle cursor-agent wrapper format
        # cursor-agent returns: {"type":"result","result":"```json\n{...}\n```",...}
        feedback_data = {}
        raw_output = result.parsed_output or {}

        # Check if this is cursor-agent wrapper format
        if isinstance(raw_output, dict) and "result" in raw_output:
            content = raw_output.get("result", "")
            # Extract JSON from markdown code block
            import re
            json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
            if json_match:
                try:
                    feedback_data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
            if not feedback_data:
                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    try:
                        feedback_data = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass
        elif isinstance(raw_output, dict) and raw_output.get("reviewer"):
            feedback_data = raw_output
        elif result.output:
            import re
            json_match = re.search(r"\{[\s\S]*\}", result.output)
            if json_match:
                try:
                    feedback_data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

        score = float(feedback_data.get("overall_code_quality", 0))
        blocking = feedback_data.get("blocking_issues", [])

        feedback = AgentFeedback(
            agent="cursor",
            approved=feedback_data.get("approved", False) and len(blocking) == 0,
            score=score,
            assessment="approved" if feedback_data.get("approved") else "needs_changes",
            concerns=[
                issue for file_review in feedback_data.get("files_reviewed", [])
                for issue in file_review.get("issues", [])
            ],
            blocking_issues=blocking,
            summary=feedback_data.get("summary", ""),
            raw_output=feedback_data,
        )

        # Save feedback
        feedback_dir = project_dir / ".workflow" / "phases" / "verification"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        (feedback_dir / "cursor_review.json").write_text(json.dumps(feedback.to_dict(), indent=2))

        logger.info(f"Cursor review: approved={feedback.approved}, score={score}")

        return {
            "verification_feedback": {"cursor": feedback},
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Cursor review failed: {e}")
        return {
            "verification_feedback": {
                "cursor": AgentFeedback(
                    agent="cursor",
                    approved=False,
                    score=0,
                    assessment="error",
                    summary=str(e),
                )
            },
            "errors": [{
                "type": "verification_error",
                "agent": "cursor",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }],
        }


async def gemini_review_node(state: WorkflowState) -> dict[str, Any]:
    """Gemini reviews the implementation for architecture.

    Args:
        state: Current workflow state

    Returns:
        State updates with gemini review feedback
    """
    logger.info("Gemini reviewing implementation...")

    project_dir = Path(state["project_dir"])
    plan = state.get("plan", {})
    impl_result = state.get("implementation_result", {})

    # Get list of changed files
    files_changed = []
    if impl_result:
        files_changed.extend(impl_result.get("files_created", []))
        files_changed.extend(impl_result.get("files_modified", []))

    if not files_changed:
        files_changed = await _get_changed_files(project_dir)

    files_list = "\n".join(f"- {f}" for f in files_changed) if files_changed else "No files specified"

    prompt = GEMINI_REVIEW_PROMPT.format(
        plan=json.dumps(plan, indent=2),
        files_list=files_list,
    )

    try:
        # Use Gemini CLI for architecture review
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

        arch_assessment = feedback_data.get("architecture_assessment", {})
        score = float(arch_assessment.get("modularity_score", 0))
        blocking = feedback_data.get("blocking_issues", [])

        feedback = AgentFeedback(
            agent="gemini",
            approved=feedback_data.get("approved", False) and len(blocking) == 0,
            score=score,
            assessment="approved" if feedback_data.get("approved") else "needs_changes",
            concerns=arch_assessment.get("concerns", []),
            blocking_issues=blocking,
            summary=feedback_data.get("summary", ""),
            raw_output=feedback_data,
        )

        # Save feedback
        feedback_dir = project_dir / ".workflow" / "phases" / "verification"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        (feedback_dir / "gemini_review.json").write_text(json.dumps(feedback.to_dict(), indent=2))

        logger.info(f"Gemini review: approved={feedback.approved}, score={score}")

        return {
            "verification_feedback": {"gemini": feedback},
            "updated_at": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Gemini review failed: {e}")
        return {
            "verification_feedback": {
                "gemini": AgentFeedback(
                    agent="gemini",
                    approved=False,
                    score=0,
                    assessment="error",
                    summary=str(e),
                )
            },
            "errors": [{
                "type": "verification_error",
                "agent": "gemini",
                "message": str(e),
                "timestamp": datetime.now().isoformat(),
            }],
        }


async def verification_fan_in_node(state: WorkflowState) -> dict[str, Any]:
    """Merge verification results and decide next step.

    Both Cursor and Gemini must approve for verification to pass.

    Args:
        state: Current workflow state with merged verification feedback

    Returns:
        State updates with verification decision
    """
    logger.info("Merging verification results...")

    project_dir = Path(state["project_dir"])
    feedback = state.get("verification_feedback", {})

    cursor_feedback = feedback.get("cursor")
    gemini_feedback = feedback.get("gemini")

    # Update phase status
    phase_status = state.get("phase_status", {}).copy()
    phase_4 = phase_status.get("4", PhaseState())
    phase_4.status = PhaseStatus.IN_PROGRESS
    phase_4.started_at = phase_4.started_at or datetime.now().isoformat()
    phase_4.attempts += 1

    if not cursor_feedback or not gemini_feedback:
        missing = []
        if not cursor_feedback:
            missing.append("cursor")
        if not gemini_feedback:
            missing.append("gemini")

        return {
            "phase_status": phase_status,
            "errors": [{
                "type": "verification_incomplete",
                "missing_agents": missing,
                "message": f"Missing review from: {', '.join(missing)}",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "retry",
        }

    # Both agents must approve
    cursor_approved = cursor_feedback.approved if hasattr(cursor_feedback, "approved") else False
    gemini_approved = gemini_feedback.approved if hasattr(gemini_feedback, "approved") else False

    cursor_score = cursor_feedback.score if hasattr(cursor_feedback, "score") else 0
    gemini_score = gemini_feedback.score if hasattr(gemini_feedback, "score") else 0
    combined_score = (cursor_score * 0.5) + (gemini_score * 0.5)

    # Collect all blocking issues
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

    # Verification threshold
    MIN_SCORE = 7.0
    approved = cursor_approved and gemini_approved and combined_score >= MIN_SCORE

    logger.info(
        f"Verification result: score={combined_score:.1f}, "
        f"cursor={cursor_approved}, gemini={gemini_approved}, "
        f"blocking={len(blocking_issues)}, approved={approved}"
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

    feedback_dir = project_dir / ".workflow" / "phases" / "verification"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    (feedback_dir / "consolidated.json").write_text(json.dumps(consolidated, indent=2))

    if approved:
        phase_4.status = PhaseStatus.COMPLETED
        phase_4.completed_at = datetime.now().isoformat()
        phase_status["4"] = phase_4

        return {
            "phase_status": phase_status,
            "current_phase": 5,
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }
    else:
        if phase_4.attempts < phase_4.max_attempts:
            phase_4.blockers = blocking_issues
            phase_status["4"] = phase_4

            return {
                "phase_status": phase_status,
                "current_phase": 3,  # Go back to implementation
                "next_decision": "retry",
                "updated_at": datetime.now().isoformat(),
            }
        else:
            phase_4.status = PhaseStatus.FAILED
            phase_4.error = f"Verification failed after {phase_4.attempts} attempts"
            phase_status["4"] = phase_4

            return {
                "phase_status": phase_status,
                "next_decision": "escalate",
                "errors": [{
                    "type": "verification_failed",
                    "combined_score": combined_score,
                    "blocking_issues": blocking_issues,
                    "message": "Code verification failed",
                    "timestamp": datetime.now().isoformat(),
                }],
            }


async def _get_changed_files(project_dir: Path) -> list[str]:
    """Get list of changed files from git.

    Args:
        project_dir: Project directory

    Returns:
        List of changed file paths
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            return [f.strip() for f in result.stdout.split("\n") if f.strip()]

    except Exception:
        pass

    return []
