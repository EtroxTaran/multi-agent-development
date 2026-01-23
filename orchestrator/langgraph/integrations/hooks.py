"""External hook script integration.

Provides a framework for external scripts to control workflow behavior.
Hooks can be used for:
- Pre/post iteration actions
- Custom verification logic
- External integration triggers
- Stop conditions

Based on Ralph Wiggum stop-hook.sh pattern.
"""

import asyncio
import logging
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default timeout for hook execution
DEFAULT_HOOK_TIMEOUT = 30

# Standard hook names
HOOK_NAMES = {
    "pre_iteration": "pre-iteration.sh",
    "post_iteration": "post-iteration.sh",
    "stop_check": "stop-check.sh",
    "pre_task": "pre-task.sh",
    "post_task": "post-task.sh",
    "on_error": "on-error.sh",
    "on_complete": "on-complete.sh",
}


@dataclass
class HookResult:
    """Result from executing a hook script.

    Attributes:
        hook_name: Name of the hook
        success: Whether hook executed successfully
        return_code: Hook script return code
        stdout: Standard output from hook
        stderr: Standard error from hook
        duration_ms: Execution duration in milliseconds
        error: Error message if hook failed to execute
    """

    hook_name: str
    success: bool
    return_code: int = 0
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "hook_name": self.hook_name,
            "success": self.success,
            "return_code": self.return_code,
            "stdout": self.stdout[:1000] if self.stdout else "",  # Truncate
            "stderr": self.stderr[:1000] if self.stderr else "",  # Truncate
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class HookManager:
    """Manages external hook scripts for workflow control.

    Hooks are shell scripts in the .workflow/hooks/ directory.
    They receive context via environment variables and can influence
    workflow behavior through return codes.

    Return codes:
    - 0: Success / Stop (for stop-check hook)
    - Non-zero: Continue / Error (context-dependent)

    Attributes:
        project_dir: Project directory
        hooks_dir: Directory containing hook scripts
        timeout: Default timeout for hook execution
        enabled: Whether hooks are enabled
        history: Execution history for debugging
    """

    project_dir: Path
    hooks_dir: Optional[Path] = None
    timeout: int = DEFAULT_HOOK_TIMEOUT
    enabled: bool = True
    history: list[HookResult] = field(default_factory=list)

    def __post_init__(self):
        """Initialize hooks directory."""
        if self.hooks_dir is None:
            self.hooks_dir = self.project_dir / ".workflow" / "hooks"

    def has_hook(self, hook_name: str) -> bool:
        """Check if a hook script exists.

        Args:
            hook_name: Hook name (e.g., "pre_iteration")

        Returns:
            True if hook script exists and is executable
        """
        if not self.enabled or not self.hooks_dir:
            return False

        script_name = HOOK_NAMES.get(hook_name, f"{hook_name}.sh")
        hook_path = self.hooks_dir / script_name

        return hook_path.exists() and _is_executable(hook_path)

    async def run_hook(
        self,
        hook_name: str,
        context: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> HookResult:
        """Run a hook script.

        Args:
            hook_name: Hook name to run
            context: Context dict to pass as environment variables
            timeout: Optional timeout override

        Returns:
            HookResult with execution details
        """
        if not self.enabled:
            return HookResult(
                hook_name=hook_name,
                success=True,
                return_code=0,
                error="Hooks disabled",
            )

        script_name = HOOK_NAMES.get(hook_name, f"{hook_name}.sh")
        hook_path = self.hooks_dir / script_name

        if not hook_path.exists():
            return HookResult(
                hook_name=hook_name,
                success=True,
                return_code=0,
                error=f"Hook not found: {script_name}",
            )

        if not _is_executable(hook_path):
            return HookResult(
                hook_name=hook_name,
                success=False,
                return_code=-1,
                error=f"Hook not executable: {script_name}",
            )

        # Build environment
        env = _build_hook_environment(context or {})

        # Execute hook
        start_time = datetime.now()
        actual_timeout = timeout or self.timeout

        try:
            process = await asyncio.create_subprocess_exec(
                str(hook_path),
                cwd=self.project_dir,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=actual_timeout,
                )

                duration_ms = (datetime.now() - start_time).total_seconds() * 1000

                result = HookResult(
                    hook_name=hook_name,
                    success=process.returncode == 0,
                    return_code=process.returncode or 0,
                    stdout=stdout.decode() if stdout else "",
                    stderr=stderr.decode() if stderr else "",
                    duration_ms=duration_ms,
                )

            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

                result = HookResult(
                    hook_name=hook_name,
                    success=False,
                    return_code=-1,
                    error=f"Hook timed out after {actual_timeout}s",
                    duration_ms=actual_timeout * 1000,
                )

        except PermissionError:
            result = HookResult(
                hook_name=hook_name,
                success=False,
                return_code=-1,
                error=f"Permission denied: {hook_path}",
            )

        except Exception as e:
            result = HookResult(
                hook_name=hook_name,
                success=False,
                return_code=-1,
                error=str(e),
            )

        # Record in history
        self.history.append(result)

        # Log result
        if result.success:
            logger.debug(f"Hook {hook_name} completed (rc={result.return_code})")
        else:
            logger.warning(f"Hook {hook_name} failed: {result.error or result.stderr}")

        return result

    async def run_stop_check(self, context: Optional[dict] = None) -> bool:
        """Run stop-check hook and return whether to stop.

        Args:
            context: Context to pass to hook

        Returns:
            True if loop should stop (hook returned 0)
        """
        result = await self.run_hook("stop_check", context)

        # Stop if hook exists and returned 0
        return result.return_code == 0 and result.error is None

    def create_hook_templates(self) -> dict[str, Path]:
        """Create template hook scripts in the hooks directory.

        Returns:
            Dict of hook name to created file path
        """
        self.hooks_dir.mkdir(parents=True, exist_ok=True)

        created = {}

        for hook_name, script_name in HOOK_NAMES.items():
            hook_path = self.hooks_dir / script_name

            if not hook_path.exists():
                template = _get_hook_template(hook_name)
                hook_path.write_text(template)
                hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
                created[hook_name] = hook_path
                logger.info(f"Created hook template: {hook_path}")

        return created

    def get_history_summary(self) -> dict:
        """Get summary of hook execution history.

        Returns:
            Summary dict with counts and timing
        """
        if not self.history:
            return {"total": 0, "success": 0, "failed": 0}

        successful = [h for h in self.history if h.success]
        failed = [h for h in self.history if not h.success]

        return {
            "total": len(self.history),
            "success": len(successful),
            "failed": len(failed),
            "avg_duration_ms": sum(h.duration_ms for h in self.history) / len(self.history),
            "recent": [h.to_dict() for h in self.history[-5:]],
        }


def _is_executable(path: Path) -> bool:
    """Check if a path is executable."""
    try:
        return os.access(path, os.X_OK)
    except Exception:
        return False


def _build_hook_environment(context: dict) -> dict:
    """Build environment variables for hook execution.

    Args:
        context: Context dict

    Returns:
        Environment dict with HOOK_ prefixed variables
    """
    env = dict(os.environ)

    # Add context as HOOK_* variables
    for key, value in context.items():
        env_key = f"HOOK_{key.upper()}"
        if isinstance(value, bool):
            env[env_key] = "true" if value else "false"
        elif isinstance(value, (list, dict)):
            import json

            env[env_key] = json.dumps(value)
        else:
            env[env_key] = str(value)

    return env


def _get_hook_template(hook_name: str) -> str:
    """Get template content for a hook script.

    Args:
        hook_name: Hook name

    Returns:
        Template script content
    """
    templates = {
        "pre_iteration": """#!/bin/bash
# Pre-iteration hook - runs before each Ralph loop iteration
# Environment: HOOK_ITERATION, HOOK_TASK_ID
# Return 0 to continue, non-zero to abort

echo "Pre-iteration hook: iteration $HOOK_ITERATION"
exit 0
""",
        "post_iteration": """#!/bin/bash
# Post-iteration hook - runs after each Ralph loop iteration
# Environment: HOOK_ITERATION, HOOK_TASK_ID, HOOK_COMPLETION_DETECTED
# Return code is logged but doesn't affect flow

echo "Post-iteration hook: iteration $HOOK_ITERATION"
exit 0
""",
        "stop_check": """#!/bin/bash
# Stop-check hook - determines whether to stop the loop
# Environment: HOOK_ITERATION, HOOK_TASK_ID, HOOK_TESTS_PASSED
# Return 0 to STOP the loop, non-zero to CONTINUE

# Example: Stop after 5 iterations regardless of test status
# if [ "$HOOK_ITERATION" -ge 5 ]; then
#     exit 0  # Stop
# fi

exit 1  # Continue
""",
        "pre_task": """#!/bin/bash
# Pre-task hook - runs before task implementation starts
# Environment: HOOK_TASK_ID, HOOK_TASK_TITLE
# Return 0 to continue, non-zero to abort

echo "Starting task: $HOOK_TASK_ID"
exit 0
""",
        "post_task": """#!/bin/bash
# Post-task hook - runs after task implementation completes
# Environment: HOOK_TASK_ID, HOOK_SUCCESS, HOOK_ITERATIONS
# Return code is logged but doesn't affect flow

echo "Task $HOOK_TASK_ID completed (success=$HOOK_SUCCESS)"
exit 0
""",
        "on_error": """#!/bin/bash
# On-error hook - runs when an error occurs
# Environment: HOOK_ERROR_TYPE, HOOK_ERROR_MESSAGE, HOOK_TASK_ID
# Can be used for notifications, logging, cleanup

echo "Error in task $HOOK_TASK_ID: $HOOK_ERROR_MESSAGE"
exit 0
""",
        "on_complete": """#!/bin/bash
# On-complete hook - runs when workflow completes successfully
# Environment: HOOK_PROJECT_NAME, HOOK_TOTAL_TASKS, HOOK_DURATION_SECONDS
# Can be used for notifications, deployment triggers

echo "Workflow complete: $HOOK_TOTAL_TASKS tasks in $HOOK_DURATION_SECONDS seconds"
exit 0
""",
    }

    return templates.get(
        hook_name,
        f"""#!/bin/bash
# Custom hook: {hook_name}
# Add your logic here

exit 0
""",
    )


def create_hook_manager(project_dir: Path, enabled: bool = True) -> HookManager:
    """Create a HookManager for a project.

    Args:
        project_dir: Project directory
        enabled: Whether hooks are enabled

    Returns:
        Configured HookManager
    """
    return HookManager(
        project_dir=project_dir,
        enabled=enabled,
    )
