"""Action logging integration for LangGraph workflow nodes.

Provides helper functions to log workflow actions from nodes.
"""

from pathlib import Path
from typing import Optional

from ...utils.action_log import ActionLog, ActionStatus, ActionType, ErrorInfo


class NodeActionLogger:
    """Helper for logging actions from workflow nodes.

    Provides convenient methods for logging common node actions
    with proper context.
    """

    def __init__(self, project_dir: str | Path, console_output: bool = True):
        """Initialize the node action logger.

        Args:
            project_dir: Project directory
            console_output: Whether to output to console
        """
        self.project_dir = Path(project_dir)
        self.workflow_dir = self.project_dir / ".workflow"
        self._action_log: Optional[ActionLog] = None

    @property
    def action_log(self) -> ActionLog:
        """Get or create action log instance."""
        if self._action_log is None:
            self._action_log = ActionLog(
                self.workflow_dir,
                console_output=True,
            )
        return self._action_log

    def log_workflow_start(self, project_name: str) -> None:
        """Log workflow start."""
        self.action_log.log(
            ActionType.WORKFLOW_START,
            f"Starting workflow for {project_name}",
            status=ActionStatus.STARTED,
            details={"project": project_name},
        )

    def log_workflow_end(self, success: bool, message: str = "") -> None:
        """Log workflow end."""
        self.action_log.log(
            ActionType.WORKFLOW_END,
            message or ("Workflow completed" if success else "Workflow failed"),
            status=ActionStatus.COMPLETED if success else ActionStatus.FAILED,
        )

    def log_phase_start(self, phase: int, phase_name: str) -> None:
        """Log phase start."""
        self.action_log.log(
            ActionType.PHASE_START,
            f"Starting {phase_name}",
            status=ActionStatus.STARTED,
            phase=phase,
        )

    def log_phase_complete(
        self,
        phase: int,
        phase_name: str,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log phase completion."""
        self.action_log.log(
            ActionType.PHASE_COMPLETE,
            f"{phase_name} completed",
            status=ActionStatus.COMPLETED,
            phase=phase,
            duration_ms=duration_ms,
        )

    def log_phase_failed(
        self,
        phase: int,
        phase_name: str,
        error: str,
    ) -> None:
        """Log phase failure."""
        self.action_log.log(
            ActionType.PHASE_FAILED,
            f"{phase_name} failed: {error[:100]}",
            status=ActionStatus.FAILED,
            phase=phase,
            error=ErrorInfo(
                error_type="phase_failure",
                message=error,
            ),
        )

    def log_phase_retry(self, phase: int, attempt: int, max_attempts: int) -> None:
        """Log phase retry."""
        self.action_log.log(
            ActionType.PHASE_RETRY,
            f"Retrying (attempt {attempt}/{max_attempts})",
            status=ActionStatus.STARTED,
            phase=phase,
            details={"attempt": attempt, "max_attempts": max_attempts},
        )

    def log_agent_invoke(
        self,
        agent: str,
        task: str,
        phase: Optional[int] = None,
    ) -> None:
        """Log agent invocation."""
        self.action_log.log(
            ActionType.AGENT_INVOKE,
            task,
            status=ActionStatus.STARTED,
            phase=phase,
            agent=agent,
        )

    def log_agent_complete(
        self,
        agent: str,
        result: str,
        phase: Optional[int] = None,
        duration_ms: Optional[float] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Log agent completion."""
        self.action_log.log(
            ActionType.AGENT_COMPLETE,
            result,
            status=ActionStatus.COMPLETED,
            phase=phase,
            agent=agent,
            duration_ms=duration_ms,
            details=details,
        )

    def log_agent_error(
        self,
        agent: str,
        error: str,
        phase: Optional[int] = None,
        exception: Optional[Exception] = None,
    ) -> None:
        """Log agent error."""
        error_info = None
        if exception:
            error_info = ErrorInfo.from_exception(exception)
        else:
            error_info = ErrorInfo(error_type="agent_error", message=error)

        self.action_log.log(
            ActionType.AGENT_ERROR,
            f"Error: {error[:100]}",
            status=ActionStatus.FAILED,
            phase=phase,
            agent=agent,
            error=error_info,
        )

    def log_task_start(
        self,
        task_id: str,
        task_title: str,
        phase: int = 3,
    ) -> None:
        """Log task start."""
        self.action_log.log(
            ActionType.TASK_START,
            f"Starting: {task_title}",
            status=ActionStatus.STARTED,
            phase=phase,
            task_id=task_id,
        )

    def log_task_complete(
        self,
        task_id: str,
        task_title: str,
        phase: int = 3,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Log task completion."""
        self.action_log.log(
            ActionType.TASK_COMPLETE,
            f"Completed: {task_title}",
            status=ActionStatus.COMPLETED,
            phase=phase,
            task_id=task_id,
            duration_ms=duration_ms,
        )

    def log_task_failed(
        self,
        task_id: str,
        error: str,
        phase: int = 3,
    ) -> None:
        """Log task failure."""
        self.action_log.log(
            ActionType.TASK_FAILED,
            f"Failed: {error[:100]}",
            status=ActionStatus.FAILED,
            phase=phase,
            task_id=task_id,
            error=ErrorInfo(error_type="task_failure", message=error),
        )

    def log_validation_pass(
        self,
        agent: str,
        score: float,
        phase: int = 2,
    ) -> None:
        """Log validation pass."""
        self.action_log.log(
            ActionType.VALIDATION_PASS,
            f"Validation approved (score: {score:.1f})",
            status=ActionStatus.COMPLETED,
            phase=phase,
            agent=agent,
            details={"score": score},
        )

    def log_validation_fail(
        self,
        agent: str,
        score: float,
        reason: str,
        phase: int = 2,
    ) -> None:
        """Log validation failure."""
        self.action_log.log(
            ActionType.VALIDATION_FAIL,
            f"Validation failed (score: {score:.1f}): {reason[:50]}",
            status=ActionStatus.FAILED,
            phase=phase,
            agent=agent,
            details={"score": score, "reason": reason},
        )

    def log_verification_pass(
        self,
        agent: str,
        score: float,
        phase: int = 4,
    ) -> None:
        """Log verification pass."""
        self.action_log.log(
            ActionType.VERIFICATION_PASS,
            f"Verification approved (score: {score:.1f})",
            status=ActionStatus.COMPLETED,
            phase=phase,
            agent=agent,
            details={"score": score},
        )

    def log_verification_fail(
        self,
        agent: str,
        score: float,
        reason: str,
        phase: int = 4,
    ) -> None:
        """Log verification failure."""
        self.action_log.log(
            ActionType.VERIFICATION_FAIL,
            f"Verification failed (score: {score:.1f}): {reason[:50]}",
            status=ActionStatus.FAILED,
            phase=phase,
            agent=agent,
            details={"score": score, "reason": reason},
        )

    def log_escalation(
        self,
        reason: str,
        phase: Optional[int] = None,
    ) -> None:
        """Log escalation to human."""
        self.action_log.log(
            ActionType.ESCALATION,
            f"Escalating: {reason}",
            status=ActionStatus.PENDING,
            phase=phase,
        )

    def log_human_input(
        self,
        input_type: str,
        phase: Optional[int] = None,
    ) -> None:
        """Log human input received."""
        self.action_log.log(
            ActionType.HUMAN_INPUT,
            f"Human input received: {input_type}",
            status=ActionStatus.COMPLETED,
            phase=phase,
        )

    def log_git_commit(
        self,
        commit_hash: str,
        message: str,
        phase: Optional[int] = None,
    ) -> None:
        """Log git commit."""
        self.action_log.log(
            ActionType.GIT_COMMIT,
            f"Committed: {commit_hash[:8]} - {message[:50]}",
            status=ActionStatus.COMPLETED,
            phase=phase,
            details={"commit_hash": commit_hash, "message": message},
        )

    def log_error(
        self,
        message: str,
        phase: Optional[int] = None,
        exception: Optional[Exception] = None,
    ) -> None:
        """Log a general error."""
        error_info = None
        if exception:
            error_info = ErrorInfo.from_exception(exception)

        self.action_log.log(
            ActionType.ERROR,
            message[:200],
            status=ActionStatus.FAILED,
            phase=phase,
            error=error_info,
        )

    def log_warning(
        self,
        message: str,
        phase: Optional[int] = None,
    ) -> None:
        """Log a warning."""
        self.action_log.log(
            ActionType.WARNING,
            message[:200],
            phase=phase,
        )

    def log_info(
        self,
        message: str,
        phase: Optional[int] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Log informational message."""
        self.action_log.log(
            ActionType.INFO,
            message[:200],
            phase=phase,
            details=details,
        )

    def log_checkpoint(
        self,
        checkpoint_id: str,
        phase: Optional[int] = None,
    ) -> None:
        """Log checkpoint creation."""
        self.action_log.log(
            ActionType.CHECKPOINT,
            f"Checkpoint created: {checkpoint_id[:16]}",
            phase=phase,
            details={"checkpoint_id": checkpoint_id},
        )


def get_node_logger(project_dir: str | Path) -> NodeActionLogger:
    """Get a node action logger for the given project.

    Args:
        project_dir: Project directory

    Returns:
        NodeActionLogger instance
    """
    return NodeActionLogger(project_dir)
