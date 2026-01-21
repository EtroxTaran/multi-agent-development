"""
Agent dispatch protocol for orchestrating specialist agents.

The AgentDispatcher is responsible for:
1. Loading agent context and configuration
2. Validating tasks fit agent capabilities
3. Executing agents with appropriate CLI
4. Validating output against schemas
5. Submitting results to review cycle

Usage:
    from orchestrator.dispatch import AgentDispatcher

    dispatcher = AgentDispatcher(project_dir)
    result = await dispatcher.dispatch("A04", task)
"""

import asyncio
import json
import logging
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from orchestrator.registry import AGENT_REGISTRY, get_agent, AgentConfig

logger = logging.getLogger(__name__)


class DispatchError(Exception):
    """Base exception for dispatch errors."""

    pass


class InvalidTaskAssignment(DispatchError):
    """Raised when a task doesn't fit an agent's capabilities."""

    def __init__(self, task_id: str, agent_id: str, reason: str):
        self.task_id = task_id
        self.agent_id = agent_id
        self.reason = reason
        super().__init__(f"Task {task_id} not suitable for {agent_id}: {reason}")


class InvalidAgentOutput(DispatchError):
    """Raised when agent output doesn't match expected schema."""

    def __init__(self, agent_id: str, errors: List[str]):
        self.agent_id = agent_id
        self.errors = errors
        super().__init__(f"Agent {agent_id} output invalid: {', '.join(errors)}")


class AgentExecutionTimeout(DispatchError):
    """Raised when agent execution times out."""

    pass


class AgentCLIError(DispatchError):
    """Raised when CLI execution fails."""

    pass


@dataclass
class Task:
    """Represents a task to be dispatched to an agent."""

    id: str
    title: str
    description: str
    acceptance_criteria: List[str]
    input_files: List[str] = field(default_factory=list)
    expected_output_files: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    iteration: int = 1
    previous_feedback: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DispatchResult:
    """Result from dispatching a task to an agent."""

    task_id: str
    agent_id: str
    status: str  # "completed", "failed", "blocked", "needs_review"
    output: Dict[str, Any]
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    execution_time_seconds: float = 0.0
    cli_used: str = ""
    iteration: int = 1
    error: Optional[str] = None
    needs_review: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "status": self.status,
            "output": self.output,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "execution_time_seconds": self.execution_time_seconds,
            "cli_used": self.cli_used,
            "iteration": self.iteration,
            "error": self.error,
            "needs_review": self.needs_review,
            "timestamp": self.timestamp.isoformat(),
        }


class AgentDispatcher:
    """Dispatches tasks to specialist agents."""

    # CLI command templates
    CLI_TEMPLATES = {
        "claude": 'claude -p "{prompt}" --output-format json --allowedTools "{tools}"',
        "cursor": 'cursor-agent --print --output-format json "{prompt}"',
        "gemini": 'gemini --yolo "{prompt}"',
    }

    def __init__(
        self,
        project_dir: Path,
        meta_architect_root: Optional[Path] = None,
    ):
        """Initialize dispatcher.

        Args:
            project_dir: Project directory where agents operate
            meta_architect_root: Root of meta-architect (for loading agent contexts)
        """
        self.project_dir = Path(project_dir)
        self.meta_architect_root = meta_architect_root or self._find_meta_architect_root()
        self._execution_log: List[Dict[str, Any]] = []

    def _find_meta_architect_root(self) -> Path:
        """Find the meta-architect root directory."""
        current = Path(__file__).parent
        while current != current.parent:
            if (current / "orchestrator").is_dir() and (current / "agents").is_dir():
                return current
            current = current.parent
        raise RuntimeError("Could not find meta-architect root directory")

    def load_agent_context(self, agent: AgentConfig) -> str:
        """Load the context file for an agent.

        Args:
            agent: Agent configuration

        Returns:
            Content of the agent's context file
        """
        if not agent.context_file:
            return ""

        context_path = self.meta_architect_root / agent.context_file
        if not context_path.exists():
            logger.warning(f"Context file not found: {context_path}")
            return ""

        return context_path.read_text()

    def load_agent_tools(self, agent: AgentConfig) -> Dict[str, Any]:
        """Load tool restrictions for an agent.

        Args:
            agent: Agent configuration

        Returns:
            Tool configuration dictionary
        """
        if not agent.tools_file:
            return {"allowed": [], "forbidden": []}

        tools_path = self.meta_architect_root / agent.tools_file
        if not tools_path.exists():
            logger.warning(f"Tools file not found: {tools_path}")
            return {"allowed": [], "forbidden": []}

        return json.loads(tools_path.read_text())

    def validate_task_for_agent(self, task: Task, agent: AgentConfig) -> bool:
        """Validate that a task is appropriate for an agent.

        Args:
            task: Task to validate
            agent: Agent to validate against

        Returns:
            True if task is valid for agent

        Raises:
            InvalidTaskAssignment: If task doesn't fit agent
        """
        import fnmatch

        # Check file write permissions
        if agent.can_write_files:
            all_output_files = task.expected_output_files + task.test_files
            for file_path in all_output_files:
                # Check forbidden paths
                for pattern in agent.forbidden_paths:
                    if fnmatch.fnmatch(file_path, pattern):
                        raise InvalidTaskAssignment(
                            task.id,
                            agent.id,
                            f"Agent forbidden from writing to '{file_path}' (matches pattern '{pattern}')",
                        )

                # Check allowed paths (if specified)
                if agent.allowed_paths:
                    allowed = False
                    for pattern in agent.allowed_paths:
                        if fnmatch.fnmatch(file_path, pattern):
                            allowed = True
                            break
                    if not allowed:
                        raise InvalidTaskAssignment(
                            task.id,
                            agent.id,
                            f"Agent not allowed to write to '{file_path}' (no matching allowed pattern)",
                        )
        elif task.expected_output_files:
            raise InvalidTaskAssignment(
                task.id,
                agent.id,
                "Agent cannot write files but task expects output files",
            )

        return True

    def build_prompt(
        self,
        task: Task,
        agent: AgentConfig,
        context: str,
    ) -> str:
        """Build the prompt for an agent execution.

        Args:
            task: Task to execute
            agent: Agent configuration
            context: Agent context content

        Returns:
            Complete prompt string
        """
        prompt_parts = []

        # Add agent context
        if context:
            prompt_parts.append(f"## Agent Context\n{context}\n")

        # Add task description
        prompt_parts.append(f"## Task: {task.title}")
        prompt_parts.append(f"\n{task.description}\n")

        # Add acceptance criteria
        if task.acceptance_criteria:
            prompt_parts.append("## Acceptance Criteria")
            for i, criterion in enumerate(task.acceptance_criteria, 1):
                prompt_parts.append(f"{i}. {criterion}")
            prompt_parts.append("")

        # Add input files
        if task.input_files:
            prompt_parts.append("## Input Files")
            for f in task.input_files:
                prompt_parts.append(f"- {f}")
            prompt_parts.append("")

        # Add expected output files
        if task.expected_output_files:
            prompt_parts.append("## Expected Output Files")
            for f in task.expected_output_files:
                prompt_parts.append(f"- {f}")
            prompt_parts.append("")

        # Add test files (for implementer to know what to test against)
        if task.test_files:
            prompt_parts.append("## Test Files")
            for f in task.test_files:
                prompt_parts.append(f"- {f}")
            prompt_parts.append("")

        # Add previous feedback if iteration > 1
        if task.iteration > 1 and task.previous_feedback:
            prompt_parts.append(f"## Previous Feedback (Iteration {task.iteration - 1})")
            for feedback in task.previous_feedback:
                reviewer = feedback.get("from_reviewer", "Unknown")
                prompt_parts.append(f"\n### From {reviewer}:")
                if feedback.get("issues"):
                    prompt_parts.append("Issues to fix:")
                    for issue in feedback["issues"]:
                        prompt_parts.append(f"- {issue}")
                if feedback.get("suggestions"):
                    prompt_parts.append("Suggestions:")
                    for suggestion in feedback["suggestions"]:
                        prompt_parts.append(f"- {suggestion}")
            prompt_parts.append("")

        # Add instructions
        prompt_parts.append("## Instructions")
        prompt_parts.append("1. Read only the files listed above")
        prompt_parts.append("2. Complete the task following acceptance criteria")
        prompt_parts.append("3. Output your result as valid JSON")
        if agent.is_reviewer:
            prompt_parts.append("4. Include score (1-10) and approved (boolean) in output")
        else:
            prompt_parts.append("4. Signal completion with: <promise>DONE</promise>")

        return "\n".join(prompt_parts)

    def get_allowed_tools_string(self, agent: AgentConfig) -> str:
        """Get comma-separated string of allowed tools for CLI.

        Args:
            agent: Agent configuration

        Returns:
            Comma-separated tools string
        """
        tools = self.load_agent_tools(agent)
        allowed = tools.get("allowed", [])

        if not allowed:
            # Default tool sets based on agent type
            if agent.is_reviewer:
                return "Read,Grep,Glob"
            elif agent.can_write_files:
                return "Read,Write,Edit,Bash(npm*),Bash(pytest*),Bash(python*),Grep,Glob"
            else:
                return "Read,Grep,Glob"

        return ",".join(allowed)

    async def execute_agent(
        self,
        cli: str,
        agent: AgentConfig,
        prompt: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute an agent using the specified CLI.

        Args:
            cli: CLI to use ("claude", "cursor", "gemini")
            agent: Agent configuration
            prompt: Prompt to send to agent
            timeout: Timeout in seconds (uses agent default if None)

        Returns:
            Agent output as dictionary

        Raises:
            AgentExecutionTimeout: If execution times out
            AgentCLIError: If CLI returns non-zero exit code
        """
        timeout = timeout or agent.timeout_seconds
        tools_string = self.get_allowed_tools_string(agent)

        # Build CLI command
        if cli == "claude":
            # Write prompt to temp file for claude (handles special chars better)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False
            ) as f:
                f.write(prompt)
                prompt_file = f.name

            cmd = [
                "claude",
                "-p",
                prompt,
                "--output-format",
                "json",
                "--allowedTools",
                tools_string,
            ]
        elif cli == "cursor":
            cmd = [
                "cursor-agent",
                "--print",
                "--output-format",
                "json",
                prompt,
            ]
        elif cli == "gemini":
            cmd = [
                "gemini",
                "--yolo",
                prompt,
            ]
        else:
            raise AgentCLIError(f"Unknown CLI: {cli}")

        logger.info(f"Executing {agent.id} ({agent.name}) with {cli}")

        start_time = datetime.utcnow()

        try:
            # Run CLI command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_dir),
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()  # Ensure process is properly reaped
                raise AgentExecutionTimeout(
                    f"Agent {agent.id} execution timed out after {timeout}s"
                )

            if process.returncode != 0:
                raise AgentCLIError(
                    f"CLI {cli} returned non-zero exit code: {process.returncode}\n"
                    f"stderr: {stderr.decode()}"
                )

            # Parse output
            output_text = stdout.decode()

            # Try to parse as JSON
            try:
                # Handle case where output contains JSON within other text
                json_start = output_text.find("{")
                json_end = output_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    output = json.loads(output_text[json_start:json_end])
                else:
                    output = {"raw_output": output_text}
            except json.JSONDecodeError:
                output = {"raw_output": output_text}

            return output

        finally:
            # Cleanup temp file if created
            if cli == "claude" and "prompt_file" in locals():
                Path(prompt_file).unlink(missing_ok=True)

    def validate_output(
        self,
        output: Dict[str, Any],
        schema_path: Optional[str],
    ) -> List[str]:
        """Validate agent output against schema.

        Args:
            output: Agent output dictionary
            schema_path: Path to JSON schema file (relative to schemas/)

        Returns:
            List of validation errors (empty if valid)
        """
        if not schema_path:
            return []

        schema_file = self.meta_architect_root / schema_path
        if not schema_file.exists():
            logger.warning(f"Schema file not found: {schema_file}")
            return []

        try:
            import jsonschema

            schema = json.loads(schema_file.read_text())
            jsonschema.validate(output, schema)
            return []
        except ImportError:
            logger.warning("jsonschema not installed, skipping validation")
            return []
        except jsonschema.ValidationError as e:
            return [str(e.message)]
        except json.JSONDecodeError as e:
            return [f"Invalid schema JSON: {e}"]

    async def dispatch(
        self,
        agent_id: str,
        task: Task,
        use_backup_cli: bool = False,
    ) -> DispatchResult:
        """Dispatch a task to an agent.

        This is the main entry point for task execution. It:
        1. Loads agent context
        2. Validates task fits agent capabilities
        3. Executes agent with appropriate CLI
        4. Validates output against schema
        5. Returns result for review submission

        Args:
            agent_id: Agent identifier (e.g., "A04")
            task: Task to execute
            use_backup_cli: Whether to use backup CLI instead of primary

        Returns:
            DispatchResult with execution details

        Raises:
            KeyError: If agent_id not found
            InvalidTaskAssignment: If task doesn't fit agent
            InvalidAgentOutput: If output doesn't match schema
        """
        agent = get_agent(agent_id)
        start_time = datetime.utcnow()

        # Step 1: Load context
        context = self.load_agent_context(agent)
        logger.info(f"Loaded context for {agent_id} ({len(context)} chars)")

        # Step 2: Validate task
        self.validate_task_for_agent(task, agent)
        logger.info(f"Task {task.id} validated for {agent_id}")

        # Step 3: Build prompt
        prompt = self.build_prompt(task, agent, context)

        # Step 4: Determine CLI
        cli = agent.backup_cli if use_backup_cli and agent.backup_cli else agent.primary_cli
        if not cli:
            raise AgentCLIError(f"No CLI available for agent {agent_id}")

        # Step 5: Execute
        try:
            output = await self.execute_agent(cli, agent, prompt)
        except AgentExecutionTimeout as e:
            return DispatchResult(
                task_id=task.id,
                agent_id=agent_id,
                status="failed",
                output={},
                cli_used=cli,
                iteration=task.iteration,
                error=str(e),
                needs_review=False,
            )
        except AgentCLIError as e:
            # Try backup CLI
            if not use_backup_cli and agent.backup_cli:
                logger.warning(f"Primary CLI failed, trying backup: {agent.backup_cli}")
                return await self.dispatch(agent_id, task, use_backup_cli=True)
            return DispatchResult(
                task_id=task.id,
                agent_id=agent_id,
                status="failed",
                output={},
                cli_used=cli,
                iteration=task.iteration,
                error=str(e),
                needs_review=False,
            )

        # Step 6: Validate output
        validation_errors = self.validate_output(output, agent.output_schema)
        if validation_errors:
            raise InvalidAgentOutput(agent_id, validation_errors)

        # Calculate execution time
        execution_time = (datetime.utcnow() - start_time).total_seconds()

        # Extract file changes from output
        files_created = output.get("files_created", [])
        files_modified = output.get("files_modified", [])

        # Determine status
        status = output.get("status", "completed")
        if status not in ["completed", "partial", "failed", "blocked", "needs_clarification"]:
            status = "completed"

        # Log execution
        self._execution_log.append({
            "task_id": task.id,
            "agent_id": agent_id,
            "cli": cli,
            "iteration": task.iteration,
            "status": status,
            "execution_time": execution_time,
            "timestamp": start_time.isoformat(),
        })

        return DispatchResult(
            task_id=task.id,
            agent_id=agent_id,
            status=status,
            output=output,
            files_created=files_created,
            files_modified=files_modified,
            execution_time_seconds=execution_time,
            cli_used=cli,
            iteration=task.iteration,
            needs_review=not agent.is_reviewer,  # Reviewers don't need review
            timestamp=start_time,
        )

    async def dispatch_reviewer(
        self,
        reviewer_id: str,
        work_to_review: Dict[str, Any],
        review_checklist: List[str],
    ) -> DispatchResult:
        """Dispatch a review request to a reviewer agent.

        Args:
            reviewer_id: Reviewer agent ID (e.g., "A07", "A08")
            work_to_review: Description of work to review
            review_checklist: Checklist items for review

        Returns:
            DispatchResult with review feedback
        """
        reviewer = get_agent(reviewer_id)
        if not reviewer.is_reviewer:
            raise InvalidTaskAssignment(
                work_to_review.get("task_id", "unknown"),
                reviewer_id,
                f"Agent {reviewer_id} is not a reviewer",
            )

        # Build review task
        task = Task(
            id=f"review-{work_to_review.get('task_id', 'unknown')}-{reviewer_id}",
            title=f"Review by {reviewer.name}",
            description=f"Review the following work:\n\n{json.dumps(work_to_review, indent=2)}",
            acceptance_criteria=review_checklist,
            input_files=work_to_review.get("files", []),
        )

        return await self.dispatch(reviewer_id, task)

    def get_execution_log(self) -> List[Dict[str, Any]]:
        """Get the execution log for this dispatcher session.

        Returns:
            List of execution log entries
        """
        return self._execution_log.copy()

    def clear_execution_log(self) -> None:
        """Clear the execution log."""
        self._execution_log.clear()


async def dispatch_parallel(
    dispatcher: AgentDispatcher,
    agent_ids: List[str],
    tasks: List[Task],
) -> List[DispatchResult]:
    """Dispatch multiple tasks to agents in parallel.

    Args:
        dispatcher: AgentDispatcher instance
        agent_ids: List of agent IDs (one per task)
        tasks: List of tasks to dispatch

    Returns:
        List of DispatchResults
    """
    if len(agent_ids) != len(tasks):
        raise ValueError("Number of agents must match number of tasks")

    coroutines = [
        dispatcher.dispatch(agent_id, task)
        for agent_id, task in zip(agent_ids, tasks)
    ]

    results = await asyncio.gather(*coroutines, return_exceptions=True)

    # Convert exceptions to failed results
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append(
                DispatchResult(
                    task_id=tasks[i].id,
                    agent_id=agent_ids[i],
                    status="failed",
                    output={},
                    error=str(result),
                    needs_review=False,
                )
            )
        else:
            processed_results.append(result)

    return processed_results
