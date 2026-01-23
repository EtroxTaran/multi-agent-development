"""Verification nodes for Phase 4.

Cursor reviews code quality and Gemini reviews architecture,
then results are merged to determine approval.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ...agents.prompts import format_prompt, load_prompt
from ...config import load_project_config
from ...config.models import get_role_assignment, infer_task_type
from ...review.resolver import ConflictResolver
from ...specialists.runner import SpecialistRunner
from ..state import (
    AgentFeedback,
    PhaseState,
    PhaseStatus,
    WorkflowState,
    create_agent_execution,
    create_error_context,
)

logger = logging.getLogger(__name__)


def _build_verification_correction_prompt(
    cursor_feedback: AgentFeedback,
    gemini_feedback: AgentFeedback,
    blocking_issues: list[str],
) -> str:
    """Build structured correction prompt for code fixes.

    Args:
        cursor_feedback: Feedback from Cursor review
        gemini_feedback: Feedback from Gemini review
        blocking_issues: List of blocking issues

    Returns:
        Formatted correction prompt string
    """
    sections = ["## Code Fixes Required\n"]
    sections.append("Your implementation was rejected. Fix these specific issues:\n")

    if blocking_issues:
        sections.append("\n### Blocking Issues (MUST FIX)\n")
        for i, issue in enumerate(blocking_issues, 1):
            sections.append(f"{i}. {issue}\n")

    # Extract specific file/line issues from cursor
    if cursor_feedback and cursor_feedback.raw_output:
        findings = cursor_feedback.raw_output.get("findings", [])
        if findings:
            sections.append("\n### 🔍 Security/Code Findings\n")
            for finding in findings[:10]:
                f = finding.get("file", "?")
                ln = finding.get("line", "?")
                desc = finding.get("description", "")
                sev = finding.get("severity", "INFO")
                sections.append(f"- `{f}:{ln}` [{sev}]: {desc}\n")

        # Check for test failures in raw output if available
        test_failures = cursor_feedback.raw_output.get("test_failures", [])
        if test_failures:
            sections.append("\n### 🧪 Test Failures\n")
            for failure in test_failures[:5]:
                sections.append(f"- {failure}\n")

    # Architecture issues from gemini
    if gemini_feedback and gemini_feedback.raw_output:
        comments = gemini_feedback.raw_output.get("comments", [])
        # Also check for 'concerns' if 'comments' is empty (standard format)
        if not comments:
            comments = gemini_feedback.raw_output.get("concerns", [])

        if comments:
            sections.append("\n### 🏛️ Architecture Issues\n")
            for c in comments[:5]:
                desc = c.get("description", str(c)) if isinstance(c, dict) else str(c)
                rec = c.get("remediation", "") if isinstance(c, dict) else ""
                if rec:
                    sections.append(f"- {desc}\n  *Fix: {rec}*\n")
                else:
                    sections.append(f"- {desc}\n")

    sections.append("\n### Instructions\n")
    sections.append("1. Fix ALL blocking issues listed above\n")
    sections.append("2. Run tests to verify fixes\n")
    sections.append("3. Ensure no new issues are introduced\n")
    return "".join(sections)


async def cursor_review_node(state: WorkflowState) -> dict[str, Any]:
    """Cursor reviews the implementation for code quality (A07-security-reviewer).

    Args:
        state: Current workflow state

    Returns:
        State updates with cursor review feedback
    """
    logger.info("Cursor reviewing implementation...")

    start_time = time.time()
    project_dir = Path(state["project_dir"])
    plan = state.get("plan", {})
    impl_result = state.get("implementation_result", {})

    if state.get("review_skipped"):
        feedback = AgentFeedback(
            agent="cursor",
            approved=True,
            score=10.0,
            assessment="skipped",
            concerns=[],
            blocking_issues=[],
            summary="Review skipped for docs-only changes.",
        )
        # Save to database
        from ...db.repositories.phase_outputs import get_phase_output_repository
        from ...storage.async_utils import run_async

        repo = get_phase_output_repository(state["project_name"])
        run_async(repo.save_cursor_review(feedback.to_dict()))
        return {
            "verification_feedback": {"cursor": feedback},
            "updated_at": datetime.now().isoformat(),
        }

    # Get list of changed files
    files_changed = []
    if impl_result:
        files_changed.extend(impl_result.get("files_created", []))
        files_changed.extend(impl_result.get("files_modified", []))

    if not files_changed:
        # Try to get from git
        files_changed = await _get_changed_files(project_dir)

    files_list = (
        "\n".join(f"- {f}" for f in files_changed) if files_changed else "No files specified"
    )

    # Get test results if available
    test_results = impl_result.get("test_results", {})
    test_results_str = (
        json.dumps(test_results, indent=2) if test_results else "No test results available"
    )

    # Build prompt from template with fallback
    try:
        template = load_prompt("cursor", "code_review")
        prompt = format_prompt(template, files_list=files_list, test_results=test_results_str)
        logger.debug("Using external cursor code review template")
    except FileNotFoundError:
        logger.debug("Cursor code review template not found, using inline prompt")
        prompt = f"""ORIGINAL PLAN:
{json.dumps(plan, indent=2)}

FILES IMPLEMENTED:
{files_list}

TEST RESULTS:
{test_results_str}"""

    try:
        runner = SpecialistRunner(project_dir)

        # Run A07-security-reviewer
        result = await asyncio.to_thread(runner.create_agent("A07-security-reviewer").run, prompt)

        if not result.success:
            raise Exception(result.error or "Cursor review failed")

        # Parse feedback
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

        score = float(feedback_data.get("score", 0))  # A07 uses "score"
        blocking = []

        # Parse findings from A07 format
        findings = feedback_data.get("findings", [])
        for finding in findings:
            severity = finding.get("severity", "INFO")
            if severity in ["CRITICAL", "HIGH"]:
                blocking.append(f"[{severity}] {finding.get('file')}: {finding.get('description')}")

        feedback = AgentFeedback(
            agent="cursor",  # Kept as "cursor" for compatibility with state schema
            approved=feedback_data.get("approved", False) and len(blocking) == 0,
            score=score,
            assessment="approved" if feedback_data.get("approved") else "needs_changes",
            concerns=findings,
            blocking_issues=blocking,
            summary=f"Security review score: {score}. {len(blocking)} blocking issues.",
            raw_output=feedback_data,
        )

        # Save feedback to database
        from ...db.repositories.phase_outputs import get_phase_output_repository
        from ...storage.async_utils import run_async

        repo = get_phase_output_repository(state["project_name"])
        run_async(repo.save_cursor_review(feedback.to_dict()))

        logger.info(f"Cursor review: approved={feedback.approved}, score={score}")

        # Track agent execution for evaluation
        execution = create_agent_execution(
            agent="cursor",
            node="cursor_review",
            template_name="code_review",
            prompt=prompt[:5000],
            output=json.dumps(feedback_data)[:10000] if feedback_data else "",
            success=True,
            exit_code=0,
            duration_seconds=(time.time() - start_time),
            model="cursor",
        )

        return {
            "verification_feedback": {"cursor": feedback},
            "updated_at": datetime.now().isoformat(),
            "last_agent_execution": execution,
            "execution_history": [execution],
        }

    except Exception as e:
        logger.error(f"Cursor review failed: {e}")

        # Create error context for fixer
        error_context = create_error_context(
            source_node="cursor_review",
            exception=e,
            state=dict(state),
            recoverable=True,
        )

        # Track failed execution
        failed_execution = create_agent_execution(
            agent="cursor",
            node="cursor_review",
            template_name="code_review",
            prompt=prompt[:5000] if "prompt" in dir() else "",
            output=str(e),
            success=False,
            exit_code=1,
            duration_seconds=(time.time() - start_time),
            error_context=error_context,
        )

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
            "errors": [
                {
                    "type": "verification_error",
                    "agent": "cursor",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "error_context": error_context,
            "last_agent_execution": failed_execution,
            "execution_history": [failed_execution],
        }


async def gemini_review_node(state: WorkflowState) -> dict[str, Any]:
    """Gemini reviews the implementation for architecture (A08-code-reviewer).

    Args:
        state: Current workflow state

    Returns:
        State updates with gemini review feedback
    """
    logger.info("Gemini reviewing implementation...")

    start_time = time.time()
    project_dir = Path(state["project_dir"])
    plan = state.get("plan", {})
    impl_result = state.get("implementation_result", {})

    if state.get("review_skipped"):
        feedback = AgentFeedback(
            agent="gemini",
            approved=True,
            score=10.0,
            assessment="skipped",
            concerns=[],
            blocking_issues=[],
            summary="Review skipped for docs-only changes.",
        )
        # Save to database
        from ...db.repositories.phase_outputs import get_phase_output_repository
        from ...storage.async_utils import run_async

        repo = get_phase_output_repository(state["project_name"])
        run_async(repo.save_gemini_review(feedback.to_dict()))
        return {
            "verification_feedback": {"gemini": feedback},
            "updated_at": datetime.now().isoformat(),
        }

    # Get list of changed files
    files_changed = []
    if impl_result:
        files_changed.extend(impl_result.get("files_created", []))
        files_changed.extend(impl_result.get("files_modified", []))

    if not files_changed:
        files_changed = await _get_changed_files(project_dir)

    files_list = (
        "\n".join(f"- {f}" for f in files_changed) if files_changed else "No files specified"
    )
    plan_json = json.dumps(plan, indent=2)

    # Build prompt from template with fallback
    try:
        template = load_prompt("gemini", "architecture_review")
        prompt = format_prompt(template, plan=plan_json, files_list=files_list)
        logger.debug("Using external gemini architecture review template")
    except FileNotFoundError:
        logger.debug("Gemini architecture review template not found, using inline prompt")
        prompt = f"""ORIGINAL PLAN:
{plan_json}

FILES IMPLEMENTED:
{files_list}"""

    try:
        runner = SpecialistRunner(project_dir)

        # Run A08-code-reviewer
        result = await asyncio.to_thread(runner.create_agent("A08-code-reviewer").run, prompt)

        if not result.success:
            raise Exception(result.error or "Gemini review failed")

        output = result.output

        # Parse feedback
        feedback_data = {}
        try:
            feedback_data = json.loads(output)
        except json.JSONDecodeError:
            json_match = re.search(r"\{[\s\S]*\}", output)
            if json_match:
                feedback_data = json.loads(json_match.group(0))

        score = float(feedback_data.get("score", 0))
        blocking = feedback_data.get("blocking_issues", [])

        # A08 uses "comments" list
        concerns = feedback_data.get("comments", [])

        feedback = AgentFeedback(
            agent="gemini",  # Kept as "gemini" for compatibility
            approved=feedback_data.get("approved", False) and len(blocking) == 0,
            score=score,
            assessment="approved" if feedback_data.get("approved") else "needs_changes",
            concerns=concerns,
            blocking_issues=blocking,
            summary=feedback_data.get("summary", ""),
            raw_output=feedback_data,
        )

        # Save feedback to database
        from ...db.repositories.phase_outputs import get_phase_output_repository
        from ...storage.async_utils import run_async

        repo = get_phase_output_repository(state["project_name"])
        run_async(repo.save_gemini_review(feedback.to_dict()))

        logger.info(f"Gemini review: approved={feedback.approved}, score={score}")

        # Track agent execution for evaluation
        execution = create_agent_execution(
            agent="gemini",
            node="gemini_review",
            template_name="architecture_review",
            prompt=prompt[:5000],
            output=output[:10000] if output else "",
            success=True,
            exit_code=0,
            duration_seconds=(time.time() - start_time),
            model="gemini",
        )

        return {
            "verification_feedback": {"gemini": feedback},
            "updated_at": datetime.now().isoformat(),
            "last_agent_execution": execution,
            "execution_history": [execution],
        }

    except Exception as e:
        logger.error(f"Gemini review failed: {e}")

        # Create error context for fixer
        error_context = create_error_context(
            source_node="gemini_review",
            exception=e,
            state=dict(state),
            recoverable=True,
        )

        # Track failed execution
        failed_execution = create_agent_execution(
            agent="gemini",
            node="gemini_review",
            template_name="architecture_review",
            prompt=prompt[:5000] if "prompt" in dir() else "",
            output=str(e),
            success=False,
            exit_code=1,
            duration_seconds=(time.time() - start_time),
            error_context=error_context,
        )

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
            "errors": [
                {
                    "type": "verification_error",
                    "agent": "gemini",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "error_context": error_context,
            "last_agent_execution": failed_execution,
            "execution_history": [failed_execution],
        }


async def review_gate_node(state: WorkflowState) -> dict[str, Any]:
    """Determine whether to skip reviews based on change risk."""
    project_dir = Path(state["project_dir"])
    config = load_project_config(project_dir)
    policy = getattr(config.workflow, "review_gating", "conservative")

    changed_files = await _collect_changed_files(state, project_dir)
    docs_only = _is_docs_only_changes(changed_files)

    skip_reviews = False
    if policy == "conservative":
        skip_reviews = bool(changed_files) and docs_only

    return {
        "review_skipped": skip_reviews,
        "review_skipped_reason": "docs_only" if skip_reviews else None,
        "review_changed_files": changed_files,
        "next_decision": "continue",
        "updated_at": datetime.now().isoformat(),
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
            "errors": [
                {
                    "type": "verification_incomplete",
                    "missing_agents": missing,
                    "message": f"Missing review from: {', '.join(missing)}",
                    "timestamp": datetime.now().isoformat(),
                }
            ],
            "next_decision": "retry",
        }

    # Get role assignment for dynamic weights based on task type
    current_task = state.get("current_task") or {}
    role = get_role_assignment(current_task)
    task_type = infer_task_type(current_task)
    logger.info(
        f"Verification using role dispatch: task_type={task_type.value}, "
        f"weights=cursor:{role.cursor_weight}/gemini:{role.gemini_weight}"
    )

    # Resolve conflicts using 4-Eyes Protocol with task-aware weights
    resolver = ConflictResolver()
    result = resolver.resolve(
        cursor_feedback,
        gemini_feedback,
        cursor_weight=role.cursor_weight,
        gemini_weight=role.gemini_weight,
    )

    logger.info(f"Verification resolution: {result.action.upper()} - {result.decision_reason}")

    # Save consolidated feedback
    consolidated = {
        "combined_score": result.final_score,
        "cursor_score": cursor_feedback.score if hasattr(cursor_feedback, "score") else 0,
        "gemini_score": gemini_feedback.score if hasattr(gemini_feedback, "score") else 0,
        "approved": result.approved,
        "decision": result.action,
        "reason": result.decision_reason,
        "blocking_issues": result.blocking_issues,
        "timestamp": datetime.now().isoformat(),
    }

    # Save consolidated feedback to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save_output(phase=4, output_type="consolidated", content=consolidated))

    if result.approved:
        phase_4.status = PhaseStatus.COMPLETED
        phase_4.completed_at = datetime.now().isoformat()
        phase_status["4"] = phase_4

        return {
            "phase_status": phase_status,
            "current_phase": 5,
            "next_decision": "continue",
            "updated_at": datetime.now().isoformat(),
        }
    elif result.action == "escalate":
        # Explicit escalation requested by resolver
        phase_4.status = PhaseStatus.FAILED
        phase_4.error = f"Verification conflict escalated: {result.decision_reason}"
        phase_status["4"] = phase_4

        return {
            "phase_status": phase_status,
            "next_decision": "escalate",
            "errors": [
                {
                    "type": "verification_conflict",
                    "message": result.decision_reason,
                    "timestamp": datetime.now().isoformat(),
                }
            ],
        }
    else:
        # Rejected - retry via Bug Fixer (or legacy implementation)
        if phase_4.attempts < phase_4.max_attempts:
            phase_4.blockers = result.blocking_issues
            phase_status["4"] = phase_4

            # Build structured correction prompt for retry
            correction_prompt = _build_verification_correction_prompt(
                cursor_feedback, gemini_feedback, result.blocking_issues
            )

            return {
                "phase_status": phase_status,
                "current_phase": 3,  # Go back to implementation/fix
                "next_decision": "retry",
                "correction_prompt": correction_prompt,
                "updated_at": datetime.now().isoformat(),
            }
        else:
            phase_4.status = PhaseStatus.FAILED
            phase_4.error = f"Verification failed after {phase_4.attempts} attempts"
            phase_status["4"] = phase_4

            return {
                "phase_status": phase_status,
                "next_decision": "escalate",
                "errors": [
                    {
                        "type": "verification_failed",
                        "combined_score": result.final_score,
                        "blocking_issues": result.blocking_issues,
                        "message": f"Code verification failed: {result.decision_reason}",
                        "timestamp": datetime.now().isoformat(),
                    }
                ],
            }


async def _get_changed_files(project_dir: Path) -> list[str]:
    """Get list of changed files from git.

    Args:
        project_dir: Project directory

    Returns:
        List of changed file paths
    """
    import subprocess

    files = set()

    try:
        # Uncommitted changes
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            files.update(f.strip() for f in result.stdout.split("\n") if f.strip())
    except Exception:
        pass

    if files:
        return sorted(files)

    try:
        # Last commit changes (useful for worktree merges)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            files.update(f.strip() for f in result.stdout.split("\n") if f.strip())
    except Exception:
        pass

    return sorted(files)


async def _collect_changed_files(state: WorkflowState, project_dir: Path) -> list[str]:
    """Collect changed files from state and git."""
    files = set()
    impl_result = state.get("implementation_result", {})
    if impl_result:
        files.update(impl_result.get("files_created", []) or [])
        files.update(impl_result.get("files_modified", []) or [])

    files.update(await _get_changed_files(project_dir))
    return sorted(f for f in files if f)


def _is_docs_only_changes(files: list[str]) -> bool:
    """Check if all changes are documentation-only."""
    if not files:
        return False

    doc_exts = {".md", ".txt", ".rst", ".adoc"}
    for file_path in files:
        path = Path(file_path)
        if path.suffix.lower() not in doc_exts:
            return False
    return True
