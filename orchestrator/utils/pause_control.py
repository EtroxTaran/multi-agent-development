"""Enhanced pause control utilities.

Provides cooperative pause checking during long-running implementations
with the ability to save partial progress and resume later.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class PauseSignal:
    """Signal returned when a pause is requested.

    Contains information needed to resume from the pause point.
    """

    pause_requested: bool
    resume_from: Optional[str] = None  # Step/node to resume from
    partial_progress: Optional[dict] = None  # Progress saved at pause
    pause_reason: Optional[str] = None
    paused_at: Optional[str] = None
    checkpoint_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "pause_requested": self.pause_requested,
            "resume_from": self.resume_from,
            "partial_progress": self.partial_progress,
            "pause_reason": self.pause_reason,
            "paused_at": self.paused_at,
            "checkpoint_id": self.checkpoint_id,
        }


@dataclass
class PauseCheckpoint:
    """Checkpoint created when pausing mid-implementation."""

    step_id: str
    step_index: int
    total_steps: int
    completed_steps: list[str] = field(default_factory=list)
    pending_steps: list[str] = field(default_factory=list)
    step_outputs: dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "step_index": self.step_index,
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "pending_steps": self.pending_steps,
            "step_outputs": self.step_outputs,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PauseCheckpoint":
        return cls(
            step_id=data.get("step_id", ""),
            step_index=data.get("step_index", 0),
            total_steps=data.get("total_steps", 0),
            completed_steps=data.get("completed_steps", []),
            pending_steps=data.get("pending_steps", []),
            step_outputs=data.get("step_outputs", {}),
            timestamp=data.get("timestamp"),
        )


class PauseController:
    """Controller for cooperative pause checking.

    Allows long-running implementations to check for pause requests
    between steps and save progress for later resumption.

    Usage:
        controller = PauseController(state_getter)

        for step in implementation_steps:
            # Check for pause before each step
            if controller.should_pause():
                checkpoint = controller.create_checkpoint(step, completed)
                return controller.pause(checkpoint)

            # Execute step
            result = execute_step(step)
            completed.append(step)
    """

    def __init__(
        self,
        state_getter: Callable[[], dict],
        on_checkpoint_save: Optional[Callable[[PauseCheckpoint], None]] = None,
    ):
        """Initialize the pause controller.

        Args:
            state_getter: Function that returns current workflow state
            on_checkpoint_save: Optional callback when checkpoint is saved
        """
        self._get_state = state_getter
        self._on_checkpoint_save = on_checkpoint_save
        self._forced_pause = False
        self._pause_reason: Optional[str] = None

    def should_pause(self) -> bool:
        """Check if a pause has been requested.

        Should be called between steps in long-running operations.

        Returns:
            True if pause was requested
        """
        if self._forced_pause:
            return True

        state = self._get_state()
        return bool(state.get("pause_requested", False))

    def get_pause_reason(self) -> Optional[str]:
        """Get the reason for the pause request.

        Returns:
            Pause reason if available
        """
        if self._pause_reason:
            return self._pause_reason

        state = self._get_state()
        return state.get("pause_reason")

    def force_pause(self, reason: str = "manual") -> None:
        """Force a pause on the next check.

        Args:
            reason: Reason for the forced pause
        """
        self._forced_pause = True
        self._pause_reason = reason
        logger.info(f"Pause forced: {reason}")

    def clear_forced_pause(self) -> None:
        """Clear a forced pause."""
        self._forced_pause = False
        self._pause_reason = None

    def create_checkpoint(
        self,
        current_step: str,
        step_index: int,
        total_steps: int,
        completed_steps: list[str],
        pending_steps: list[str],
        step_outputs: Optional[dict] = None,
    ) -> PauseCheckpoint:
        """Create a checkpoint at the current position.

        Args:
            current_step: ID of the current step
            step_index: Index of current step
            total_steps: Total number of steps
            completed_steps: List of completed step IDs
            pending_steps: List of pending step IDs
            step_outputs: Optional outputs from completed steps

        Returns:
            PauseCheckpoint with resume information
        """
        checkpoint = PauseCheckpoint(
            step_id=current_step,
            step_index=step_index,
            total_steps=total_steps,
            completed_steps=completed_steps,
            pending_steps=pending_steps,
            step_outputs=step_outputs or {},
            timestamp=datetime.now().isoformat(),
        )

        if self._on_checkpoint_save:
            self._on_checkpoint_save(checkpoint)

        logger.info(f"Created pause checkpoint at step {step_index}/{total_steps}: {current_step}")

        return checkpoint

    def pause(
        self,
        checkpoint: PauseCheckpoint,
        reason: Optional[str] = None,
    ) -> PauseSignal:
        """Create a pause signal with checkpoint.

        Args:
            checkpoint: Checkpoint to include in the signal
            reason: Optional reason for pausing

        Returns:
            PauseSignal for returning from the operation
        """
        return PauseSignal(
            pause_requested=True,
            resume_from=checkpoint.step_id,
            partial_progress=checkpoint.to_dict(),
            pause_reason=reason or self.get_pause_reason() or "user_requested",
            paused_at=datetime.now().isoformat(),
            checkpoint_id=f"pause-{checkpoint.step_id}-{checkpoint.step_index}",
        )


async def with_pause_check(
    steps: list[Any],
    step_executor: Callable[[Any], Any],
    pause_controller: PauseController,
    step_id_getter: Callable[[Any], str] = lambda s: str(s),
    resume_from: Optional[str] = None,
) -> tuple[list[Any], Optional[PauseSignal]]:
    """Execute steps with pause checking between each.

    Args:
        steps: List of steps to execute
        step_executor: Async function to execute each step
        pause_controller: PauseController instance
        step_id_getter: Function to get step ID from step object
        resume_from: Optional step ID to resume from

    Returns:
        Tuple of (results, pause_signal if paused)
    """
    results: list[Any] = []
    completed_step_ids: list[str] = []
    step_outputs: dict[str, Any] = {}

    # Find resume point if specified
    start_index = 0
    if resume_from:
        for i, step in enumerate(steps):
            if step_id_getter(step) == resume_from:
                start_index = i
                break

    total_steps = len(steps)

    for i in range(start_index, total_steps):
        step = steps[i]
        step_id = step_id_getter(step)

        # Check for pause before executing
        if pause_controller.should_pause():
            pending_ids = [step_id_getter(s) for s in steps[i:]]
            checkpoint = pause_controller.create_checkpoint(
                current_step=step_id,
                step_index=i,
                total_steps=total_steps,
                completed_steps=completed_step_ids,
                pending_steps=pending_ids,
                step_outputs=step_outputs,
            )
            return results, pause_controller.pause(checkpoint)

        # Execute step
        try:
            result = await step_executor(step)
            results.append(result)
            completed_step_ids.append(step_id)
            step_outputs[step_id] = result
        except Exception as e:
            logger.error(f"Step {step_id} failed: {e}")
            raise

    return results, None


class PauseAwareBatchExecutor:
    """Executor for batch operations that respects pause requests.

    Useful for operations like applying multiple file changes
    or running multiple tests.

    Usage:
        executor = PauseAwareBatchExecutor(pause_controller)

        async for result in executor.execute_batch(items, process_item):
            # Process each result
            pass

        if executor.was_paused:
            return executor.get_pause_signal()
    """

    def __init__(
        self,
        pause_controller: PauseController,
        check_interval: int = 5,  # Check every N items
    ):
        """Initialize the batch executor.

        Args:
            pause_controller: PauseController instance
            check_interval: How often to check for pause (every N items)
        """
        self._controller = pause_controller
        self._check_interval = check_interval
        self._was_paused = False
        self._pause_signal: Optional[PauseSignal] = None
        self._completed_items: list[str] = []
        self._pending_items: list[str] = []
        self._item_results: dict[str, Any] = {}

    @property
    def was_paused(self) -> bool:
        """Check if execution was paused."""
        return self._was_paused

    def get_pause_signal(self) -> Optional[PauseSignal]:
        """Get the pause signal if paused."""
        return self._pause_signal

    async def execute_batch(
        self,
        items: list[Any],
        processor: Callable[[Any], Any],
        item_id_getter: Callable[[Any], str] = lambda x: str(x),
    ):
        """Execute a batch of items with pause checking.

        Args:
            items: Items to process
            processor: Async function to process each item
            item_id_getter: Function to get item ID

        Yields:
            Results from processing each item
        """
        total = len(items)

        for i, item in enumerate(items):
            item_id = item_id_getter(item)

            # Check for pause at intervals
            if i % self._check_interval == 0 and self._controller.should_pause():
                self._was_paused = True
                self._pending_items = [item_id_getter(x) for x in items[i:]]

                checkpoint = self._controller.create_checkpoint(
                    current_step=item_id,
                    step_index=i,
                    total_steps=total,
                    completed_steps=self._completed_items,
                    pending_steps=self._pending_items,
                    step_outputs=self._item_results,
                )
                self._pause_signal = self._controller.pause(checkpoint)
                return

            # Process item
            result = await processor(item)
            self._completed_items.append(item_id)
            self._item_results[item_id] = result

            yield result

    def get_progress(self) -> dict:
        """Get current progress information.

        Returns:
            Progress dictionary
        """
        total = len(self._completed_items) + len(self._pending_items)
        completed = len(self._completed_items)

        return {
            "total": total,
            "completed": completed,
            "pending": len(self._pending_items),
            "progress_percent": (completed / total * 100) if total > 0 else 0,
            "was_paused": self._was_paused,
        }


def create_pause_state_updates(pause_signal: PauseSignal) -> dict:
    """Create state updates for a pause signal.

    Args:
        pause_signal: The pause signal

    Returns:
        Dictionary of state updates
    """
    return {
        "paused_at_node": pause_signal.resume_from,
        "paused_at_timestamp": pause_signal.paused_at,
        "pause_reason": pause_signal.pause_reason,
        # Don't set pause_requested=False here - that's handled by resume
    }


def create_resume_state_updates() -> dict:
    """Create state updates for resuming from pause.

    Returns:
        Dictionary of state updates
    """
    return {
        "pause_requested": False,
        "paused_at_node": None,
        "paused_at_timestamp": None,
        "pause_reason": None,
    }
