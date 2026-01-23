"""Agent adapter layer for universal loop execution.

Provides a uniform interface for running any agent (Claude, Cursor, Gemini)
in an iterative loop pattern. Each adapter handles CLI-specific differences
like command building, completion detection, and model selection.

Usage:
    from orchestrator.agents.adapter import create_adapter, AgentType

    adapter = create_adapter(AgentType.CLAUDE, project_dir)
    result = await adapter.run_iteration(prompt, timeout=300)

    if adapter.detect_completion(result.output):
        print("Task completed!")
"""

import asyncio
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..config.models import (
    CLAUDE_MODELS, DEFAULT_CLAUDE_MODEL,
    GEMINI_MODELS, DEFAULT_GEMINI_MODEL,
    CURSOR_MODELS, DEFAULT_CURSOR_MODEL
)

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Supported agent types."""
    CLAUDE = "claude"
    CURSOR = "cursor"
    GEMINI = "gemini"


@dataclass
class AgentCapabilities:
    """Capabilities of an agent adapter.

    Attributes:
        supports_json_output: Whether agent can output structured JSON
        supports_session: Whether agent supports session continuity
        supports_model_selection: Whether agent supports model override
        supports_plan_mode: Whether agent supports plan mode
        supports_budget_flag: Whether agent supports --max-budget-usd
        available_models: List of available model names
        completion_patterns: Patterns that signal task completion
        default_model: Default model to use if none specified
    """
    supports_json_output: bool = False
    supports_session: bool = False
    supports_model_selection: bool = False
    supports_plan_mode: bool = False
    supports_budget_flag: bool = False
    available_models: list[str] = field(default_factory=list)
    completion_patterns: list[str] = field(default_factory=list)
    default_model: Optional[str] = None


@dataclass
class IterationResult:
    """Result from a single loop iteration.

    Attributes:
        success: Whether iteration completed without errors
        output: Raw output text
        parsed_output: Parsed JSON output if available
        completion_detected: Whether completion pattern was found
        exit_code: Process exit code
        duration_seconds: Execution duration
        error: Error message if failed
        files_changed: List of files modified during iteration
        session_id: Session ID if using session continuity
        cost_usd: Estimated cost if available
        model: Model used for this iteration
    """
    success: bool
    output: str = ""
    parsed_output: Optional[dict] = None
    completion_detected: bool = False
    exit_code: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    files_changed: list[str] = field(default_factory=list)
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "success": self.success,
            "output": self.output[:2000] if self.output else "",  # Truncate for storage
            "parsed_output": self.parsed_output,
            "completion_detected": self.completion_detected,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "files_changed": self.files_changed,
            "session_id": self.session_id,
            "cost_usd": self.cost_usd,
            "model": self.model,
        }


class AgentAdapter(ABC):
    """Base class for agent adapters.

    Each adapter provides a uniform interface for running an agent
    in an iterative loop, handling CLI-specific differences.
    """

    def __init__(
        self,
        project_dir: Path,
        model: Optional[str] = None,
        timeout: int = 300,
    ):
        """Initialize the adapter.

        Args:
            project_dir: Project directory to run in
            model: Optional model override
            timeout: Default timeout in seconds
        """
        self.project_dir = Path(project_dir)
        self.model = model
        self.timeout = timeout

    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        """Get the agent type."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> AgentCapabilities:
        """Get agent capabilities."""
        pass

    @abstractmethod
    def build_command(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_turns: int = 15,
        allowed_tools: Optional[list[str]] = None,
        session_id: Optional[str] = None,
        budget_usd: Optional[float] = None,
        use_plan_mode: bool = False,
        **kwargs,
    ) -> list[str]:
        """Build the CLI command for this agent.

        Args:
            prompt: The prompt to send
            model: Model override
            max_turns: Maximum turns per invocation
            allowed_tools: List of allowed tools
            session_id: Optional session ID for continuity
            budget_usd: Budget limit for this invocation
            use_plan_mode: Whether to use plan mode
            **kwargs: Additional agent-specific arguments

        Returns:
            Command as list of strings
        """
        pass

    @abstractmethod
    def detect_completion(self, output: str) -> bool:
        """Detect if the output signals task completion.

        Args:
            output: Raw output from agent

        Returns:
            True if completion detected
        """
        pass

    async def run_iteration(
        self,
        prompt: str,
        timeout: Optional[int] = None,
        model: Optional[str] = None,
        max_turns: int = 15,
        allowed_tools: Optional[list[str]] = None,
        session_id: Optional[str] = None,
        budget_usd: Optional[float] = None,
        use_plan_mode: bool = False,
        **kwargs,
    ) -> IterationResult:
        """Run a single iteration with this agent.

        Args:
            prompt: The prompt to send
            timeout: Timeout in seconds (uses default if not specified)
            model: Model override
            max_turns: Maximum turns per invocation
            allowed_tools: List of allowed tools
            session_id: Optional session ID for continuity
            budget_usd: Budget limit for this invocation
            use_plan_mode: Whether to use plan mode
            **kwargs: Additional agent-specific arguments

        Returns:
            IterationResult with execution details
        """
        timeout = timeout or self.timeout
        model = model or self.model

        cmd = self.build_command(
            prompt=prompt,
            model=model,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
            session_id=session_id,
            budget_usd=budget_usd,
            use_plan_mode=use_plan_mode,
            **kwargs,
        )

        start_time = datetime.now()
        process = None

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "TERM": "dumb"},
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            duration = (datetime.now() - start_time).total_seconds()
            output_text = stdout.decode() if stdout else ""
            error_text = stderr.decode() if stderr else ""

            # Parse JSON output if available
            parsed_output = self._parse_output(output_text)

            # Detect completion
            completion_detected = self.detect_completion(output_text)

            # Extract files changed
            files_changed = self._extract_files_changed(output_text, parsed_output)

            # Extract cost if available
            cost_usd = self._extract_cost(parsed_output)

            # Extract session ID if available
            extracted_session_id = self._extract_session_id(output_text, parsed_output)

            if process.returncode != 0:
                return IterationResult(
                    success=False,
                    output=output_text,
                    parsed_output=parsed_output,
                    completion_detected=completion_detected,
                    exit_code=process.returncode,
                    duration_seconds=duration,
                    error=error_text or f"Exit code: {process.returncode}",
                    files_changed=files_changed,
                    session_id=extracted_session_id or session_id,
                    cost_usd=cost_usd,
                    model=model,
                )

            return IterationResult(
                success=True,
                output=output_text,
                parsed_output=parsed_output,
                completion_detected=completion_detected,
                exit_code=process.returncode,
                duration_seconds=duration,
                files_changed=files_changed,
                session_id=extracted_session_id or session_id,
                cost_usd=cost_usd,
                model=model,
            )

        except asyncio.TimeoutError:
            duration = (datetime.now() - start_time).total_seconds()
            if process is not None:
                await self._terminate_process(process)
            return IterationResult(
                success=False,
                exit_code=-1,
                duration_seconds=duration,
                error=f"Timeout after {timeout} seconds",
            )

        except asyncio.CancelledError:
            if process is not None:
                await self._terminate_process(process)
            raise

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            if process is not None:
                await self._terminate_process(process)
            logger.error(f"Error running {self.agent_type.value}: {e}")
            return IterationResult(
                success=False,
                exit_code=-1,
                duration_seconds=duration,
                error=str(e),
            )

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        """Safely terminate a subprocess."""
        if process.returncode is not None:
            return

        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Process didn't terminate gracefully, sending SIGKILL")
                process.kill()
                await process.wait()
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error(f"Error terminating process: {e}")

    def _parse_output(self, output: str) -> Optional[dict]:
        """Parse JSON from output."""
        if not output:
            return None

        # Try direct JSON parse
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass

        # Look for JSON block in output
        json_match = re.search(r"\{[\s\S]*\}", output)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _extract_files_changed(
        self,
        output: str,
        parsed_output: Optional[dict],
    ) -> list[str]:
        """Extract list of changed files from output."""
        files = []

        if parsed_output:
            files.extend(parsed_output.get("files_modified", []))
            files.extend(parsed_output.get("files_created", []))

        return list(set(files))

    def _extract_cost(self, parsed_output: Optional[dict]) -> Optional[float]:
        """Extract cost from parsed output."""
        if not parsed_output:
            return None

        cost = parsed_output.get("cost_usd")
        if cost is not None:
            return float(cost)

        usage = parsed_output.get("usage", {})
        if usage:
            return usage.get("cost_usd")

        return None

    def _extract_session_id(
        self,
        output: str,
        parsed_output: Optional[dict],
    ) -> Optional[str]:
        """Extract session ID from output."""
        if parsed_output:
            session_id = parsed_output.get("session_id")
            if session_id:
                return session_id

        # Try to extract from output text
        session_match = re.search(r'session[_-]?id["\']?\s*:\s*["\']?([a-zA-Z0-9_-]+)', output, re.IGNORECASE)
        if session_match:
            return session_match.group(1)

        return None


class ClaudeAdapter(AgentAdapter):
    """Adapter for Claude Code CLI.

    Full-featured adapter with support for:
    - Session continuity (--resume, --session-id)
    - Plan mode (--permission-mode plan)
    - Budget control (--max-budget-usd)
    - JSON schema validation (--json-schema)
    - Model selection (sonnet, opus, haiku)

    Completion signal: <promise>DONE</promise>
    """

    COMPLETION_PATTERNS = [
        "<promise>DONE</promise>",
        '"status": "completed"',
        '"status":"completed"',
    ]

    AVAILABLE_MODELS = CLAUDE_MODELS

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CLAUDE

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_json_output=True,
            supports_session=True,
            supports_model_selection=True,
            supports_plan_mode=True,
            supports_budget_flag=True,
            available_models=self.AVAILABLE_MODELS,
            completion_patterns=self.COMPLETION_PATTERNS,
            default_model=DEFAULT_CLAUDE_MODEL,
        )

    def build_command(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_turns: int = 15,
        allowed_tools: Optional[list[str]] = None,
        session_id: Optional[str] = None,
        budget_usd: Optional[float] = None,
        use_plan_mode: bool = False,
        resume_session: bool = False,
        json_schema: Optional[str] = None,
        fallback_model: str = DEFAULT_CLAUDE_MODEL,
        **kwargs,
    ) -> list[str]:
        """Build Claude CLI command."""
        cmd = ["claude", "-p", prompt, "--output-format", "json"]

        # Model selection
        if model and model in self.AVAILABLE_MODELS:
            cmd.extend(["--model", model])

        # Session handling
        if session_id:
            if resume_session:
                cmd.extend(["--resume", session_id])
            else:
                cmd.extend(["--session-id", session_id])

        # Plan mode
        if use_plan_mode:
            cmd.extend(["--permission-mode", "plan"])

        # Budget control
        if budget_usd is not None:
            cmd.extend(["--max-budget-usd", str(budget_usd)])

        # JSON schema validation
        if json_schema:
            cmd.extend(["--json-schema", json_schema])

        # Fallback model
        if fallback_model:
            cmd.extend(["--fallback-model", fallback_model])

        # Allowed tools
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        # Max turns
        cmd.extend(["--max-turns", str(max_turns)])

        return cmd

    def detect_completion(self, output: str) -> bool:
        """Detect completion in Claude output."""
        for pattern in self.COMPLETION_PATTERNS:
            if pattern in output:
                return True
        return False


class CursorAdapter(AgentAdapter):
    """Adapter for Cursor Code CLI.

    Supports model selection:
    - codex-5.2: High capability model
    - composer: Cheaper, faster model

    Completion signals:
    - {"status": "done"}
    - {"status": "completed"}
    """

    COMPLETION_PATTERNS = [
        '"status": "done"',
        '"status":"done"',
        '"status": "completed"',
        '"status":"completed"',
    ]

    AVAILABLE_MODELS = CURSOR_MODELS

    @property
    def agent_type(self) -> AgentType:
        return AgentType.CURSOR

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_json_output=True,
            supports_session=False,
            supports_model_selection=True,
            supports_plan_mode=False,
            supports_budget_flag=False,
            available_models=self.AVAILABLE_MODELS,
            completion_patterns=self.COMPLETION_PATTERNS,
            default_model=DEFAULT_CURSOR_MODEL,
        )

    def build_command(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_turns: int = 15,
        allowed_tools: Optional[list[str]] = None,
        session_id: Optional[str] = None,
        budget_usd: Optional[float] = None,
        use_plan_mode: bool = False,
        force: bool = True,
        **kwargs,
    ) -> list[str]:
        """Build Cursor CLI command.

        Note: cursor-agent uses --print for non-interactive mode,
        prompt is a positional argument at the end.
        """
        cmd = ["cursor-agent", "--print", "--output-format", "json"]

        # Model selection (if supported by cursor-agent)
        if model and model in self.AVAILABLE_MODELS:
            cmd.extend(["--model", model])

        # Force non-interactive
        if force:
            cmd.append("--force")

        # Prompt must be positional at the end
        cmd.append(prompt)

        return cmd

    def detect_completion(self, output: str) -> bool:
        """Detect completion in Cursor output."""
        for pattern in self.COMPLETION_PATTERNS:
            if pattern in output:
                return True
        return False


class GeminiAdapter(AgentAdapter):
    """Adapter for Gemini CLI.

    Supports model selection:
    - gemini-2.0-flash: Fast, cost-effective
    - gemini-2.0-pro: Higher capability

    Completion signals (text patterns):
    - DONE
    - COMPLETE
    - FINISHED
    """

    COMPLETION_PATTERNS = [
        "DONE",
        "COMPLETE",
        "FINISHED",
        '"status": "done"',
        '"status": "completed"',
    ]

    AVAILABLE_MODELS = GEMINI_MODELS

    @property
    def agent_type(self) -> AgentType:
        return AgentType.GEMINI

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            supports_json_output=False,  # Gemini CLI doesn't support --output-format
            supports_session=False,
            supports_model_selection=True,
            supports_plan_mode=False,
            supports_budget_flag=False,
            available_models=self.AVAILABLE_MODELS,
            completion_patterns=self.COMPLETION_PATTERNS,
            default_model=DEFAULT_GEMINI_MODEL,
        )

    def build_command(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_turns: int = 15,
        allowed_tools: Optional[list[str]] = None,
        session_id: Optional[str] = None,
        budget_usd: Optional[float] = None,
        use_plan_mode: bool = False,
        **kwargs,
    ) -> list[str]:
        """Build Gemini CLI command.

        Note: Gemini uses --yolo for auto-approve, prompt is positional.
        Does NOT support --output-format flag.
        """
        cmd = ["gemini"]

        # Model selection
        if model and model in self.AVAILABLE_MODELS:
            cmd.extend(["--model", model])

        # Auto-approve tool calls
        cmd.append("--yolo")

        # Prompt as positional argument
        cmd.append(prompt)

        return cmd

    def detect_completion(self, output: str) -> bool:
        """Detect completion in Gemini output.

        Uses text pattern matching since Gemini doesn't output structured JSON.
        """
        # Check for explicit completion markers
        for pattern in self.COMPLETION_PATTERNS:
            # Case-insensitive for text patterns
            if pattern in output or pattern.lower() in output.lower():
                return True

        # Check for JSON-like completion (in case Gemini outputs JSON)
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict):
                status = parsed.get("status", "").lower()
                if status in ("done", "completed", "finished"):
                    return True
        except json.JSONDecodeError:
            pass

        return False


# Agent adapter registry
ADAPTER_REGISTRY: dict[AgentType, type[AgentAdapter]] = {
    AgentType.CLAUDE: ClaudeAdapter,
    AgentType.CURSOR: CursorAdapter,
    AgentType.GEMINI: GeminiAdapter,
}


def create_adapter(
    agent_type: AgentType | str,
    project_dir: Path,
    model: Optional[str] = None,
    timeout: int = 300,
) -> AgentAdapter:
    """Create an agent adapter by type.

    Args:
        agent_type: Agent type (AgentType enum or string)
        project_dir: Project directory to run in
        model: Optional model override
        timeout: Default timeout in seconds

    Returns:
        Configured agent adapter

    Raises:
        ValueError: If agent_type is not recognized
    """
    if isinstance(agent_type, str):
        try:
            agent_type = AgentType(agent_type.lower())
        except ValueError:
            raise ValueError(
                f"Unknown agent type: {agent_type}. "
                f"Available: {[t.value for t in AgentType]}"
            )

    adapter_class = ADAPTER_REGISTRY.get(agent_type)
    if not adapter_class:
        raise ValueError(f"No adapter registered for agent type: {agent_type}")

    return adapter_class(project_dir, model=model, timeout=timeout)


def get_agent_capabilities(agent_type: AgentType | str) -> AgentCapabilities:
    """Get capabilities for an agent type without creating an adapter.

    Args:
        agent_type: Agent type

    Returns:
        AgentCapabilities for the agent type
    """
    if isinstance(agent_type, str):
        agent_type = AgentType(agent_type.lower())

    adapter_class = ADAPTER_REGISTRY.get(agent_type)
    if not adapter_class:
        raise ValueError(f"Unknown agent type: {agent_type}")

    # Create a temporary instance to get capabilities
    # Using a dummy path since we just need the capabilities
    return adapter_class(Path(".")).capabilities


def get_available_agents() -> list[AgentType]:
    """Get list of all available agent types."""
    return list(ADAPTER_REGISTRY.keys())


def get_agent_for_task(
    task: dict,
    default_agent: AgentType = AgentType.CLAUDE,
    default_model: Optional[str] = None,
) -> tuple[AgentType, Optional[str]]:
    """Determine which agent and model to use for a task.

    Checks task metadata, environment variables, and falls back to defaults.

    Args:
        task: Task dictionary with optional agent/model hints
        default_agent: Default agent type
        default_model: Default model

    Returns:
        Tuple of (agent_type, model)
    """
    # Check environment variable overrides
    env_agent = os.environ.get("LOOP_AGENT")
    env_model = os.environ.get("LOOP_MODEL")

    if env_agent:
        try:
            agent_type = AgentType(env_agent.lower())
        except ValueError:
            logger.warning(f"Invalid LOOP_AGENT: {env_agent}, using default")
            agent_type = default_agent
    else:
        # Check task metadata
        task_agent = task.get("agent_type") or task.get("primary_cli")
        if task_agent:
            try:
                agent_type = AgentType(task_agent.lower())
            except ValueError:
                agent_type = default_agent
        else:
            agent_type = default_agent

    # Model selection
    model = env_model or task.get("model") or default_model

    # Validate model for agent
    capabilities = get_agent_capabilities(agent_type)
    if model and capabilities.available_models and model not in capabilities.available_models:
        logger.warning(
            f"Model {model} not available for {agent_type.value}, "
            f"using {capabilities.default_model}"
        )
        model = capabilities.default_model

    return agent_type, model
