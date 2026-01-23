"""Base agent class for CLI wrappers with audit trail integration."""

import json
import logging
import os
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default timeouts by phase (in seconds)
PHASE_TIMEOUTS = {
    1: 900,  # Planning: 15 minutes
    2: 600,  # Validation: 10 minutes
    3: 1800,  # Implementation: 30 minutes
    4: 600,  # Verification: 10 minutes
    5: 300,  # Completion: 5 minutes
}


@dataclass
class AgentResult:
    """Result from an agent execution.

    Attributes:
        success: Whether the execution succeeded
        output: Raw stdout output
        parsed_output: Parsed JSON output if available
        error: Error message if failed
        exit_code: Process exit code
        duration_seconds: Execution duration
        session_id: Session ID if using session continuity
        cost_usd: Estimated cost if available
        model: Model used if known
        schema_validated: Whether output was validated against a schema
        validation_errors: List of validation errors if schema validation failed
        evaluation: Evaluation result if evaluation was run
    """

    success: bool
    output: Optional[str] = None
    parsed_output: Optional[dict] = None
    error: Optional[str] = None
    exit_code: int = 0
    duration_seconds: float = 0.0
    session_id: Optional[str] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None
    schema_validated: bool = False
    validation_errors: Optional[list[str]] = None
    evaluation: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "parsed_output": self.parsed_output,
            "error": self.error,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "session_id": self.session_id,
            "cost_usd": self.cost_usd,
            "model": self.model,
            "schema_validated": self.schema_validated,
            "validation_errors": self.validation_errors,
            "evaluation": self.evaluation,
        }


class BaseAgent(ABC):
    """Base class for CLI agent wrappers.

    Provides common functionality for all CLI agent wrappers:
    - Command building and execution
    - Timeout management
    - Output parsing
    - Audit trail integration (optional)
    - Auto-improvement evaluation (optional)
    """

    name: str = "base"

    def __init__(
        self,
        project_dir: str | Path,
        timeout: int = 300,
        phase_timeouts: Optional[dict[int, int]] = None,
        enable_audit: bool = True,
        enable_evaluation: bool = False,
    ):
        """Initialize the agent.

        Args:
            project_dir: Root directory of the project
            timeout: Default timeout in seconds for command execution
            phase_timeouts: Optional per-phase timeout overrides
            enable_audit: Whether to enable audit trail logging
            enable_evaluation: Whether to enable auto-improvement evaluation
        """
        self.project_dir = Path(project_dir)
        self.timeout = timeout
        self.phase_timeouts = phase_timeouts or PHASE_TIMEOUTS.copy()
        self.enable_audit = enable_audit
        self.enable_evaluation = enable_evaluation

        # Lazily initialized audit trail
        self._audit_trail = None

        # Lazily initialized evaluator
        self._evaluator = None

    @property
    def audit_trail(self):
        """Get or create the audit trail.

        Uses the storage adapter layer which automatically selects
        between file-based and SurrealDB backends.
        """
        if self._audit_trail is None and self.enable_audit:
            try:
                from ..storage import get_audit_storage

                self._audit_trail = get_audit_storage(self.project_dir)
            except ImportError:
                # Fallback to direct audit trail if storage module not available
                try:
                    from ..audit import get_project_audit_trail

                    self._audit_trail = get_project_audit_trail(self.project_dir)
                except ImportError:
                    logger.debug("Audit trail not available")
        return self._audit_trail

    @property
    def evaluator(self):
        """Get or create the evaluator for auto-improvement.

        Returns:
            AgentEvaluator instance or None if not enabled
        """
        if self._evaluator is None and self.enable_evaluation:
            try:
                from ..evaluation import AgentEvaluator

                self._evaluator = AgentEvaluator(
                    project_dir=self.project_dir,
                    evaluator_model="haiku",
                    enable_storage=True,
                )
            except ImportError:
                logger.debug("Evaluation module not available")
        return self._evaluator

    @abstractmethod
    def build_command(self, prompt: str, **kwargs) -> list[str]:
        """Build the CLI command to execute.

        Args:
            prompt: The prompt to send to the agent
            **kwargs: Additional arguments

        Returns:
            Command as list of strings
        """
        pass

    def get_timeout_for_phase(self, phase_num: Optional[int] = None) -> int:
        """Get the timeout for a specific phase.

        Args:
            phase_num: Phase number (1-5), or None for default timeout

        Returns:
            Timeout in seconds
        """
        if phase_num is not None and phase_num in self.phase_timeouts:
            return self.phase_timeouts[phase_num]
        return self.timeout

    def run(
        self,
        prompt: str,
        output_file: Optional[Path] = None,
        phase: Optional[int] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> AgentResult:
        """Execute the agent with the given prompt.

        Args:
            prompt: The prompt to send to the agent
            output_file: Optional file to write output to
            phase: Optional phase number for phase-specific timeout
            task_id: Optional task ID for audit trail
            session_id: Optional session ID for continuity
            **kwargs: Additional arguments passed to build_command

        Returns:
            AgentResult with execution details
        """
        command = self.build_command(prompt, **kwargs)
        timeout = self.get_timeout_for_phase(phase)

        # Use context manager for audit if enabled and task_id provided
        if self.audit_trail and task_id:
            return self._run_with_audit(
                command=command,
                prompt=prompt,
                output_file=output_file,
                phase=phase,
                task_id=task_id,
                session_id=session_id,
                timeout=timeout,
                **kwargs,
            )
        else:
            return self._run_without_audit(
                command=command,
                output_file=output_file,
                session_id=session_id,
                timeout=timeout,
            )

    def _run_with_audit(
        self,
        command: list[str],
        prompt: str,
        output_file: Optional[Path],
        phase: Optional[int],
        task_id: str,
        session_id: Optional[str],
        timeout: int,
        **kwargs,
    ) -> AgentResult:
        """Run command with audit trail recording."""
        metadata = {"phase": phase, **{k: str(v)[:100] for k, v in kwargs.items() if v}}

        with self.audit_trail.record(
            agent=self.name,
            task_id=task_id,
            prompt=prompt,
            session_id=session_id,
            command_args=command,
            metadata=metadata,
        ) as audit_entry:
            result = self._execute_command(command, output_file, session_id, timeout)

            # Set result on audit entry
            audit_entry.set_result(
                success=result.success,
                exit_code=result.exit_code,
                output_length=len(result.output) if result.output else 0,
                error_length=len(result.error) if result.error else 0,
                cost_usd=result.cost_usd,
                model=result.model,
                parsed_output_type=type(result.parsed_output).__name__
                if result.parsed_output
                else None,
            )

            return result

    def _run_without_audit(
        self,
        command: list[str],
        output_file: Optional[Path],
        session_id: Optional[str],
        timeout: int,
    ) -> AgentResult:
        """Run command without audit trail."""
        return self._execute_command(command, output_file, session_id, timeout)

    def _execute_command(
        self,
        command: list[str],
        output_file: Optional[Path],
        session_id: Optional[str],
        timeout: int,
    ) -> AgentResult:
        """Execute the actual subprocess command."""
        start_time = time.time()

        try:
            result = subprocess.run(
                command,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "TERM": "dumb"},
            )

            duration = time.time() - start_time
            output = result.stdout
            stderr = result.stderr

            # Try to parse JSON output
            parsed_output = None
            if output:
                try:
                    parsed_output = json.loads(output)
                except json.JSONDecodeError:
                    # Output is not JSON, that's fine
                    pass

            # Write to output file if specified
            if output_file and output:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, "w") as f:
                    if parsed_output:
                        json.dump(parsed_output, f, indent=2)
                    else:
                        f.write(output)

            # Extract additional info from parsed output
            cost_usd = None
            model = None
            if parsed_output:
                cost_usd = parsed_output.get("cost_usd") or parsed_output.get("usage", {}).get(
                    "cost_usd"
                )
                model = parsed_output.get("model")

            if result.returncode != 0:
                return AgentResult(
                    success=False,
                    output=output,
                    parsed_output=parsed_output,
                    error=stderr or f"Exit code: {result.returncode}",
                    exit_code=result.returncode,
                    duration_seconds=duration,
                    session_id=session_id,
                    cost_usd=cost_usd,
                    model=model,
                )

            return AgentResult(
                success=True,
                output=output,
                parsed_output=parsed_output,
                exit_code=result.returncode,
                duration_seconds=duration,
                session_id=session_id,
                cost_usd=cost_usd,
                model=model,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return AgentResult(
                success=False,
                error=f"Command timed out after {timeout} seconds",
                exit_code=-1,
                duration_seconds=duration,
            )

        except FileNotFoundError as e:
            cli_cmd = self.get_cli_command()
            error_msg = f"CLI not found: {cli_cmd}. Is it installed? Error: {e}"
            return AgentResult(
                success=False,
                error=error_msg,
                exit_code=-1,
                duration_seconds=0,
            )

        except PermissionError as e:
            cli_cmd = self.get_cli_command()
            error_msg = f"Permission denied executing {cli_cmd}: {e}"
            return AgentResult(
                success=False,
                error=error_msg,
                exit_code=-1,
                duration_seconds=0,
            )

        except OSError as e:
            cli_cmd = self.get_cli_command()
            error_msg = f"OS error executing {cli_cmd}: {e}"
            duration = time.time() - start_time
            return AgentResult(
                success=False,
                error=error_msg,
                exit_code=-1,
                duration_seconds=duration,
            )

        except Exception as e:
            # Log unexpected exceptions for debugging
            cli_cmd = self.get_cli_command()
            error_msg = f"Unexpected error: {type(e).__name__}: {e}"
            duration = time.time() - start_time
            logger.error(f"Unexpected error in {cli_cmd}: {type(e).__name__}: {e}")
            return AgentResult(
                success=False,
                error=error_msg,
                exit_code=-1,
                duration_seconds=duration,
            )

    def check_available(self) -> bool:
        """Check if the CLI tool is available."""
        try:
            result = subprocess.run(
                [self.get_cli_command(), "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @abstractmethod
    def get_cli_command(self) -> str:
        """Get the main CLI command name."""
        pass

    def get_context_file(self) -> Optional[Path]:
        """Get the context file path for this agent."""
        return None

    def read_context_file(self) -> Optional[str]:
        """Read the context file content if it exists."""
        context_file = self.get_context_file()
        if context_file and context_file.exists():
            return context_file.read_text()
        return None

    def get_execution_context(
        self,
        prompt: str,
        result: AgentResult,
        task_id: Optional[str] = None,
        node: Optional[str] = None,
        template_name: Optional[str] = None,
    ) -> dict:
        """Build execution context for evaluation.

        This method creates the context dictionary that can be used
        for post-execution evaluation in the workflow.

        Args:
            prompt: The prompt sent to the agent
            result: The execution result
            task_id: Optional task ID
            node: Optional node name
            template_name: Optional prompt template name

        Returns:
            Execution context dictionary
        """
        return {
            "agent": self.name,
            "node": node or f"{self.name}_execution",
            "prompt": prompt,
            "output": result.output or "",
            "parsed_output": result.parsed_output,
            "success": result.success,
            "session_id": result.session_id,
            "cost_usd": result.cost_usd,
            "model": result.model,
            "task_id": task_id,
            "template_name": template_name or "default",
            "duration_seconds": result.duration_seconds,
        }

    # Schema cache for validation
    _schema_cache: dict[str, dict] = {}

    def validate_output(
        self,
        parsed_output: dict,
        schema_name: str,
        strict: bool = False,
    ) -> tuple[bool, list[str]]:
        """Validate parsed output against a JSON schema.

        Args:
            parsed_output: The parsed JSON output to validate
            schema_name: Name of the schema file (e.g., 'plan-schema.json')
            strict: If True, validation failures are treated as errors

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        try:
            import jsonschema
        except ImportError:
            logger.warning("jsonschema not installed - skipping validation")
            return (True, [])  # Degrade gracefully

        schema = self._load_schema(schema_name)
        if schema is None:
            if strict:
                return (False, [f"Schema '{schema_name}' not found"])
            return (True, [])

        try:
            jsonschema.validate(instance=parsed_output, schema=schema)
            return (True, [])
        except jsonschema.ValidationError as e:
            errors = [
                f"Validation error at {'.'.join(str(p) for p in e.absolute_path)}: {e.message}"
            ]
            return (False, errors)
        except jsonschema.SchemaError as e:
            errors = [f"Invalid schema '{schema_name}': {e.message}"]
            return (False, errors)

    def _load_schema(self, schema_name: str) -> Optional[dict]:
        """Load and cache a JSON schema.

        Schemas are searched in:
        1. project_dir/schemas/
        2. orchestrator/schemas/
        3. ~/.config/conductor/schemas/

        Args:
            schema_name: Name of the schema file

        Returns:
            Schema dict or None if not found
        """
        if schema_name in self._schema_cache:
            return self._schema_cache[schema_name]

        # Search paths for schemas
        search_paths = [
            self.project_dir / "schemas" / schema_name,
            Path(__file__).parent.parent / "schemas" / schema_name,
            Path.home() / ".config" / "conductor" / "schemas" / schema_name,
        ]

        for path in search_paths:
            if path.exists():
                try:
                    schema = json.loads(path.read_text())
                    self._schema_cache[schema_name] = schema
                    return schema
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in schema {path}: {e}")
                    return None

        logger.debug(f"Schema '{schema_name}' not found in search paths")
        return None
