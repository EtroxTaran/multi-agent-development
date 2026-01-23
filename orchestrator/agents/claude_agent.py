"""Claude Code CLI agent wrapper with enhanced features.

Supports advanced CLI features:
- Plan Mode: --permission-mode plan for complex tasks
- Session Continuity: --resume and --session-id for iteration context
- JSON Schema Validation: --json-schema for structured output
- Budget Control: --max-budget-usd for cost management
- Fallback Model: --fallback-model for resilience

Reference: https://docs.anthropic.com/claude-code/cli
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..config.models import DEFAULT_CLAUDE_MODEL
from .base import AgentResult, BaseAgent
from .prompts import format_prompt, load_prompt

if TYPE_CHECKING:
    from ..storage import SessionStorageAdapter


# Complexity thresholds for plan mode
PLAN_MODE_FILE_THRESHOLD = 3  # Use plan mode if touching >= 3 files
PLAN_MODE_ALWAYS_COMPLEXITIES = ["high"]  # Always use plan mode for these


class ClaudeAgent(BaseAgent):
    """Wrapper for Claude Code CLI with enhanced features.

    Claude Code is used for planning and implementation phases.
    It reads context from CLAUDE.md and .claude/system.md.

    Enhanced features:
    - Plan mode detection based on task complexity
    - Session continuity for iterative refinement
    - JSON schema validation for structured output
    - Budget control per-invocation
    - Fallback model configuration
    """

    name = "claude"

    def __init__(
        self,
        project_dir: str | Path,
        timeout: int = 600,
        allowed_tools: Optional[list[str]] = None,
        system_prompt_file: Optional[str] = None,
        phase_timeouts: Optional[dict[int, int]] = None,
        enable_audit: bool = True,
        # Enhanced features
        enable_session_continuity: bool = True,
        default_fallback_model: Optional[str] = DEFAULT_CLAUDE_MODEL,
        default_budget_usd: Optional[float] = None,
        schema_dir: Optional[Path] = None,
    ):
        """Initialize Claude agent.

        Args:
            project_dir: Root directory of the project
            timeout: Timeout in seconds (default 10 minutes for complex tasks)
            allowed_tools: List of allowed tool patterns
            system_prompt_file: Path to system prompt file relative to project
            phase_timeouts: Optional per-phase timeout overrides
            enable_audit: Whether to enable audit trail logging

            Enhanced features:
            enable_session_continuity: Enable session tracking for iterative tasks
            default_fallback_model: Default fallback model (sonnet, haiku)
            default_budget_usd: Default budget limit per invocation
            schema_dir: Directory containing JSON schemas
        """
        super().__init__(project_dir, timeout, phase_timeouts, enable_audit)
        self.allowed_tools = allowed_tools or [
            "Bash(git*)",
            "Bash(npm*)",
            "Bash(pytest*)",
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
        ]
        self.system_prompt_file = system_prompt_file

        # Enhanced features
        self.enable_session_continuity = enable_session_continuity
        self.default_fallback_model = default_fallback_model
        self.default_budget_usd = default_budget_usd
        self.schema_dir = schema_dir or self._find_schema_dir()

        # Session manager for continuity (uses storage adapter)
        self._session_manager: Optional["SessionStorageAdapter"] = None
        if enable_session_continuity:
            from ..storage import get_session_storage

            self._session_manager = get_session_storage(project_dir)

    def _find_schema_dir(self) -> Optional[Path]:
        """Find the schemas directory."""
        # Try to find relative to project
        for parent in [self.project_dir, self.project_dir.parent]:
            schema_dir = parent / "schemas"
            if schema_dir.is_dir():
                return schema_dir
        return None

    @property
    def session_manager(self) -> Optional["SessionStorageAdapter"]:
        """Get the session storage adapter."""
        return self._session_manager

    def get_cli_command(self) -> str:
        """Get the CLI command."""
        return "claude"

    def get_context_file(self) -> Optional[Path]:
        """Get Claude's context file."""
        return self.project_dir / "CLAUDE.md"

    def should_use_plan_mode(
        self,
        files_to_create: Optional[list[str]] = None,
        files_to_modify: Optional[list[str]] = None,
        estimated_complexity: Optional[str] = None,
    ) -> bool:
        """Determine if plan mode should be used for a task.

        Plan mode (`--permission-mode plan`) makes Claude:
        1. First explore and analyze the codebase
        2. Present a detailed plan for approval
        3. Only then execute the plan

        This is valuable for complex tasks to ensure good architecture.

        Args:
            files_to_create: List of files to create
            files_to_modify: List of files to modify
            estimated_complexity: Complexity estimate (low, medium, high)

        Returns:
            True if plan mode should be used
        """
        # Always use plan mode for high complexity tasks
        if estimated_complexity in PLAN_MODE_ALWAYS_COMPLEXITIES:
            return True

        # Use plan mode if touching many files
        total_files = len(files_to_create or []) + len(files_to_modify or [])
        if total_files >= PLAN_MODE_FILE_THRESHOLD:
            return True

        return False

    def build_command(
        self,
        prompt: str,
        output_format: str = "json",
        max_turns: Optional[int] = None,
        # Enhanced features
        use_plan_mode: bool = False,
        task_id: Optional[str] = None,
        resume_session: bool = True,
        output_schema: Optional[str] = None,
        budget_usd: Optional[float] = None,
        fallback_model: Optional[str] = None,
        **kwargs,
    ) -> list[str]:
        """Build the Claude CLI command with enhanced features.

        Args:
            prompt: The prompt to send
            output_format: Output format (json, text, stream-json)
            max_turns: Maximum number of agentic turns

            Enhanced features:
            use_plan_mode: Use --permission-mode plan
            task_id: Task ID for session management
            resume_session: Whether to resume existing session
            output_schema: Path to JSON schema file (relative to schema_dir)
            budget_usd: Maximum budget for this invocation
            fallback_model: Fallback model (sonnet, haiku)
            **kwargs: Additional arguments (ignored)

        Returns:
            Command as list of strings
        """
        command = [
            "claude",
            "-p",
            prompt,
            "--output-format",
            output_format,
        ]

        # Plan mode for complex tasks
        if use_plan_mode:
            command.extend(["--permission-mode", "plan"])

        # Session continuity
        if task_id and self._session_manager:
            if resume_session:
                resume_args = self._session_manager.get_resume_args(task_id)
                if resume_args:
                    command.extend(resume_args)
                else:
                    # New session - set session ID for tracking
                    session_args = self._session_manager.get_session_id_args(task_id)
                    command.extend(session_args)
            else:
                # Explicitly not resuming - create new session
                session = self._session_manager.create_session(task_id)
                command.extend(["--session-id", session.session_id])

        # JSON schema validation
        if output_schema and self.schema_dir:
            schema_path = self.schema_dir / output_schema
            if schema_path.exists():
                command.extend(["--json-schema", str(schema_path)])

        # Budget control
        effective_budget = budget_usd or self.default_budget_usd
        if effective_budget is not None:
            command.extend(["--max-budget-usd", str(effective_budget)])

        # Fallback model
        effective_fallback = fallback_model or self.default_fallback_model
        if effective_fallback:
            command.extend(["--fallback-model", effective_fallback])

        # Add system prompt file if specified
        if self.system_prompt_file:
            system_path = self.project_dir / self.system_prompt_file
            if system_path.exists():
                command.extend(
                    [
                        "--append-system-prompt-file",
                        str(system_path),
                    ]
                )

        # Add allowed tools
        if self.allowed_tools:
            tools_str = ",".join(self.allowed_tools)
            command.extend(["--allowedTools", tools_str])

        # Add max turns if specified
        if max_turns:
            command.extend(["--max-turns", str(max_turns)])

        return command

    def run(
        self,
        prompt: str,
        output_file: Optional[Path] = None,
        phase: Optional[int] = None,
        # Enhanced features
        task_id: Optional[str] = None,
        use_plan_mode: Optional[bool] = None,
        output_schema: Optional[str] = None,
        budget_usd: Optional[float] = None,
        **kwargs,
    ) -> AgentResult:
        """Execute the agent with enhanced features.

        Args:
            prompt: The prompt to send to the agent
            output_file: Optional file to write output to
            phase: Optional phase number for phase-specific timeout
            task_id: Task ID for session management
            use_plan_mode: Whether to use plan mode (auto-detect if None)
            output_schema: JSON schema for output validation
            budget_usd: Budget limit for this invocation
            **kwargs: Additional arguments passed to build_command

        Returns:
            AgentResult with execution details
        """
        # Auto-detect plan mode if not specified
        if use_plan_mode is None and "files_to_create" in kwargs:
            use_plan_mode = self.should_use_plan_mode(
                files_to_create=kwargs.get("files_to_create"),
                files_to_modify=kwargs.get("files_to_modify"),
                estimated_complexity=kwargs.get("estimated_complexity"),
            )

        # Run with enhanced features
        result = super().run(
            prompt=prompt,
            output_file=output_file,
            phase=phase,
            task_id=task_id,
            use_plan_mode=use_plan_mode or False,
            output_schema=output_schema,
            budget_usd=budget_usd,
            **kwargs,
        )

        # Update session after successful run
        if task_id and self._session_manager and result.success:
            self._session_manager.touch_session(task_id)

            # Try to capture session ID from output
            if result.output:
                self._session_manager.capture_session_id_from_output(task_id, result.output)

        return result

    def run_planning(
        self,
        product_spec: str,
        output_file: Optional[Path] = None,
        task_id: Optional[str] = None,
        strict_validation: bool = True,
    ) -> AgentResult:
        """Run Claude for planning phase with plan mode.

        Uses plan mode by default since planning is inherently complex.

        Args:
            product_spec: Content of PRODUCT.md
            output_file: File to write plan to
            task_id: Optional task ID for session tracking
            strict_validation: If True, fail on schema validation errors

        Returns:
            AgentResult with the plan
        """
        try:
            template = load_prompt("claude", "planning")
            prompt = format_prompt(template, product_spec=product_spec)
        except FileNotFoundError:
            # Fallback to inline prompt if template not found
            prompt = f"""You are a senior software architect. Analyze the following product specification and create a detailed implementation plan.

PRODUCT SPECIFICATION:
{product_spec}

Create a JSON response with the following structure:
{{
    "plan_name": "Name of the feature/project",
    "summary": "Brief summary of what will be built",
    "phases": [
        {{
            "phase": 1,
            "name": "Phase name",
            "tasks": [
                {{
                    "id": "T1",
                    "description": "Task description",
                    "files": ["list of files to create/modify"],
                    "dependencies": []
                }}
            ]
        }}
    ],
    "test_strategy": {{
        "unit_tests": ["List of unit test files"],
        "integration_tests": ["List of integration tests"],
        "test_commands": ["Commands to run tests"]
    }},
    "risks": ["List of potential risks"],
    "estimated_complexity": "low|medium|high"
}}

Focus on:
1. Breaking work into small, testable tasks
2. Identifying all files that need to be created or modified
3. Defining clear dependencies between tasks
4. Planning tests before implementation (TDD approach)"""

        result = self.run(
            prompt,
            output_file=output_file,
            use_plan_mode=True,  # Always use plan mode for planning
            task_id=task_id,
            output_schema="plan-schema.json",
        )

        # Perform schema validation for planning output
        if result.success and result.parsed_output:
            is_valid, errors = self.validate_output(
                result.parsed_output,
                "plan-schema.json",
                strict=strict_validation,
            )
            result.schema_validated = is_valid
            result.validation_errors = errors if errors else None

            if strict_validation and not is_valid:
                result.success = False
                result.error = f"Schema validation failed: {'; '.join(errors)}"

        return result

    def run_implementation(
        self,
        plan: dict,
        feedback: Optional[dict] = None,
        output_file: Optional[Path] = None,
        task_id: Optional[str] = None,
    ) -> AgentResult:
        """Run Claude for implementation phase.

        Uses plan mode if the plan indicates high complexity.

        Args:
            plan: The approved plan from Phase 1
            feedback: Consolidated feedback from Phase 2
            output_file: File to write results to
            task_id: Task ID for session tracking

        Returns:
            AgentResult with implementation details
        """
        feedback_section = ""
        if feedback:
            feedback_section = f"""

FEEDBACK TO ADDRESS:
{json.dumps(feedback, indent=2)}
"""

        # Count files to determine complexity
        files_to_create = []
        files_to_modify = []
        for phase in plan.get("phases", []):
            for task in phase.get("tasks", []):
                files = task.get("files", [])
                for f in files:
                    # Heuristic: existing files are modified, new files created
                    if (self.project_dir / f).exists():
                        files_to_modify.append(f)
                    else:
                        files_to_create.append(f)

        try:
            template = load_prompt("claude", "implementation")
            prompt = format_prompt(
                template,
                plan=json.dumps(plan, indent=2),
                feedback_section=feedback_section,
            )
        except FileNotFoundError:
            # Fallback to inline prompt if template not found
            prompt = f"""You are implementing a software feature based on an approved plan.

IMPLEMENTATION PLAN:
{json.dumps(plan, indent=2)}
{feedback_section}

INSTRUCTIONS:
1. Write tests FIRST (TDD approach)
2. Implement the code to make tests pass
3. Follow the task order and dependencies
4. Report progress as JSON

For each task you complete, output a JSON object:
{{
    "task_id": "T1",
    "status": "completed",
    "files_created": ["list of new files"],
    "files_modified": ["list of modified files"],
    "tests_written": ["list of test files"],
    "tests_passed": true,
    "notes": "Any implementation notes"
}}

At the end, provide a summary:
{{
    "implementation_complete": true,
    "all_tests_pass": true,
    "total_files_created": 5,
    "total_files_modified": 3,
    "test_results": {{
        "passed": 10,
        "failed": 0,
        "skipped": 0
    }}
}}"""

        use_plan_mode = self.should_use_plan_mode(
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
            estimated_complexity=plan.get("estimated_complexity"),
        )

        return self.run(
            prompt,
            output_file=output_file,
            max_turns=50,
            task_id=task_id,
            use_plan_mode=use_plan_mode,
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
        )

    def run_task(
        self,
        task: dict[str, Any],
        output_file: Optional[Path] = None,
        resume_session: bool = True,
    ) -> AgentResult:
        """Run Claude for a single task implementation.

        Automatically determines whether to use plan mode based on
        task complexity (files affected, estimated complexity).

        Args:
            task: Task definition with id, title, files_to_create, etc.
            output_file: File to write results to
            resume_session: Whether to resume existing session

        Returns:
            AgentResult with task completion details
        """
        task_id = task.get("id", "unknown")
        title = task.get("title", "")
        description = task.get("description", task.get("user_story", ""))
        files_to_create = task.get("files_to_create", [])
        files_to_modify = task.get("files_to_modify", [])
        test_files = task.get("test_files", [])
        acceptance_criteria = task.get("acceptance_criteria", [])
        estimated_complexity = task.get("estimated_complexity")

        try:
            template = load_prompt("claude", "task")
            prompt = format_prompt(
                template,
                task_id=task_id,
                title=title,
                description=description,
                acceptance_criteria=acceptance_criteria,
                files_to_create=files_to_create,
                files_to_modify=files_to_modify,
                test_files=test_files,
            )
        except FileNotFoundError:
            # Fallback to inline prompt if template not found
            prompt = f"""## Task: {task_id} - {title}

{description}

## Acceptance Criteria
{self._format_criteria(acceptance_criteria)}

## Files to Create
{self._format_list(files_to_create)}

## Files to Modify
{self._format_list(files_to_modify)}

## Test Files
{self._format_list(test_files)}

## Instructions
1. Implement using TDD (write/update tests first)
2. Follow existing code patterns in the project
3. Signal completion with: <promise>DONE</promise>

## Output
When complete, output a JSON object:
{{
    "task_id": "{task_id}",
    "status": "completed",
    "files_created": [],
    "files_modified": [],
    "tests_written": [],
    "tests_passed": true,
    "implementation_notes": "Brief notes"
}}"""

        use_plan_mode = self.should_use_plan_mode(
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
            estimated_complexity=estimated_complexity,
        )

        return self.run(
            prompt,
            output_file=output_file,
            task_id=task_id,
            use_plan_mode=use_plan_mode,
            resume_session=resume_session,
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
            estimated_complexity=estimated_complexity,
        )

    def close_task_session(self, task_id: str) -> bool:
        """Close session for a completed task.

        Call this when a task is fully completed or failed permanently.

        Args:
            task_id: Task identifier

        Returns:
            True if session was closed
        """
        if self._session_manager:
            return self._session_manager.close_session(task_id)
        return False

    def _format_criteria(self, criteria: list[str]) -> str:
        """Format acceptance criteria."""
        if not criteria:
            return "- No specific criteria defined"
        return "\n".join(f"- [ ] {c}" for c in criteria)

    def _format_list(self, items: list[str]) -> str:
        """Format a file list."""
        if not items:
            return "- None"
        return "\n".join(f"- {item}" for item in items)
