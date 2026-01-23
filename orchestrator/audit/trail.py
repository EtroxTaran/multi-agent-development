"""Comprehensive audit trail for CLI invocations.

Records every CLI invocation with:
- Full command (with prompt hash for privacy)
- Timing information
- Exit codes and output status
- Session IDs
- Parsed output (if available)
- Cost information (if available)

Storage: Append-only JSONL format for efficient querying.

Usage:
    trail = AuditTrail(project_dir)

    # Record an invocation
    with trail.record("claude", "T1", prompt) as entry:
        result = run_cli_command(...)
        entry.set_result(result)

    # Query audit log
    entries = trail.query(task_id="T1")
    for entry in entries:
        print(f"{entry.timestamp}: {entry.agent} - {entry.status}")

    # Get summary statistics
    stats = trail.get_statistics()
    print(f"Total invocations: {stats['total']}")
    print(f"Success rate: {stats['success_rate']:.1%}")
"""

import hashlib
import json
import logging
import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default storage location
DEFAULT_AUDIT_DIR = ".workflow/audit"
DEFAULT_LOG_FILE = "invocations.jsonl"

# Log rotation settings
MAX_LOG_SIZE_MB = 50
MAX_LOG_AGE_DAYS = 30


@dataclass
class AuditEntry:
    """A single audit log entry for a CLI invocation.

    Captures all relevant information about an agent invocation
    for debugging, analysis, and compliance purposes.

    Attributes:
        id: Unique entry identifier
        timestamp: When the invocation started
        agent: Agent identifier (claude, cursor, gemini)
        task_id: Task this invocation belongs to
        session_id: Session ID if using session continuity
        prompt_hash: SHA-256 hash of the prompt (for privacy)
        prompt_length: Length of the prompt in characters
        command_args: CLI arguments (excluding prompt content)
        exit_code: Process exit code
        status: Outcome status (success, failed, timeout, error)
        duration_seconds: Execution duration
        output_length: Length of stdout in characters
        error_length: Length of stderr in characters
        parsed_output_type: Type of parsed output if any
        cost_usd: Estimated cost if available
        model: Model used if specified
        metadata: Additional metadata
    """

    id: str
    timestamp: str
    agent: str
    task_id: str
    session_id: Optional[str] = None
    prompt_hash: str = ""
    prompt_length: int = 0
    command_args: list[str] = field(default_factory=list)
    exit_code: int = 0
    status: str = "pending"
    duration_seconds: float = 0.0
    output_length: int = 0
    error_length: int = 0
    parsed_output_type: Optional[str] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    # Internal tracking (not serialized)
    _start_time: Optional[datetime] = field(default=None, repr=False)
    _prompt: Optional[str] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """Serialize for JSONL storage."""
        data = asdict(self)
        # Remove internal fields
        data.pop("_start_time", None)
        data.pop("_prompt", None)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        """Deserialize from JSONL."""
        # Remove any fields not in the dataclass
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def set_result(
        self,
        success: bool,
        exit_code: int,
        output: Optional[str] = None,
        error: Optional[str] = None,
        parsed_output: Optional[dict] = None,
        cost_usd: Optional[float] = None,
    ) -> None:
        """Set the result of the invocation.

        Args:
            success: Whether the invocation succeeded
            exit_code: Process exit code
            output: Stdout content
            error: Stderr content
            parsed_output: Parsed output dictionary
            cost_usd: Cost in USD
        """
        if self._start_time:
            self.duration_seconds = (datetime.now() - self._start_time).total_seconds()

        self.exit_code = exit_code
        self.status = "success" if success else "failed"
        self.output_length = len(output) if output else 0
        self.error_length = len(error) if error else 0

        if parsed_output:
            self.parsed_output_type = type(parsed_output).__name__
            # Extract model from output if available
            if "model" in parsed_output:
                self.model = parsed_output["model"]

        if cost_usd is not None:
            self.cost_usd = cost_usd

    def set_timeout(self, timeout_seconds: float) -> None:
        """Mark the invocation as timed out."""
        self.status = "timeout"
        self.duration_seconds = timeout_seconds
        self.exit_code = -1

    def set_error(self, error_message: str) -> None:
        """Mark the invocation as errored."""
        self.status = "error"
        self.metadata["error_message"] = error_message
        if self._start_time:
            self.duration_seconds = (datetime.now() - self._start_time).total_seconds()


@dataclass
class AuditConfig:
    """Configuration for audit trail.

    Attributes:
        audit_dir: Directory for audit logs
        log_file: Name of the log file
        max_log_size_mb: Maximum log file size before rotation
        max_log_age_days: Maximum age of log entries
        include_prompt_preview: Include first N chars of prompt
        prompt_preview_length: Length of prompt preview
        enabled: Whether audit logging is enabled
    """

    audit_dir: str = DEFAULT_AUDIT_DIR
    log_file: str = DEFAULT_LOG_FILE
    max_log_size_mb: int = MAX_LOG_SIZE_MB
    max_log_age_days: int = MAX_LOG_AGE_DAYS
    include_prompt_preview: bool = False
    prompt_preview_length: int = 100
    enabled: bool = True


class AuditTrail:
    """Comprehensive audit trail for CLI invocations.

    Thread-safe append-only logging of all agent invocations.
    Supports querying, statistics, and log rotation.

    Usage:
        trail = AuditTrail(project_dir)

        # Context manager for automatic timing
        with trail.record("claude", "T1", prompt) as entry:
            result = subprocess.run(...)
            entry.set_result(result.returncode == 0, result.returncode, ...)

        # Or manual recording
        entry = trail.start_entry("claude", "T1", prompt)
        # ... run command ...
        entry.set_result(...)
        trail.commit_entry(entry)
    """

    def __init__(
        self,
        project_dir: Path | str,
        config: Optional[AuditConfig] = None,
    ):
        """Initialize audit trail.

        Args:
            project_dir: Project directory
            config: Audit configuration
        """
        self.project_dir = Path(project_dir)
        self.config = config or AuditConfig()

        self.audit_dir = self.project_dir / self.config.audit_dir
        self.log_file = self.audit_dir / self.config.log_file

        self._lock = threading.Lock()
        self._entry_counter = 0

        if self.config.enabled:
            self.audit_dir.mkdir(parents=True, exist_ok=True)

    def _generate_entry_id(self) -> str:
        """Generate unique entry ID.

        Note: This method must be called with self._lock held to ensure
        thread-safe counter increments. If called without lock protection,
        duplicate or skipped IDs may occur.
        """
        # Counter increment is protected by self._lock (caller must hold lock)
        self._entry_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"audit-{timestamp}-{self._entry_counter:04d}"

    def _hash_prompt(self, prompt: str) -> str:
        """Create SHA-256 hash of prompt for privacy."""
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def _extract_command_args(self, command: list[str], prompt: str) -> list[str]:
        """Extract command arguments, excluding the prompt itself."""
        # Remove prompt from command list for logging
        return [arg for arg in command if arg != prompt]

    def start_entry(
        self,
        agent: str,
        task_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        command: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> AuditEntry:
        """Start a new audit entry.

        Call this before executing a CLI command.

        Args:
            agent: Agent identifier
            task_id: Task ID
            prompt: The prompt being sent
            session_id: Session ID if using continuity
            command: Full CLI command
            metadata: Additional metadata

        Returns:
            New AuditEntry to track the invocation
        """
        # Generate entry ID under lock to ensure thread-safe counter increment
        with self._lock:
            entry_id = self._generate_entry_id()

        entry = AuditEntry(
            id=entry_id,
            timestamp=datetime.now().isoformat(),
            agent=agent,
            task_id=task_id,
            session_id=session_id,
            prompt_hash=self._hash_prompt(prompt),
            prompt_length=len(prompt),
            command_args=self._extract_command_args(command or [], prompt),
            metadata=metadata or {},
        )

        # Store internal tracking data
        entry._start_time = datetime.now()
        entry._prompt = prompt

        # Include prompt preview if configured
        if self.config.include_prompt_preview:
            preview = prompt[: self.config.prompt_preview_length]
            if len(prompt) > self.config.prompt_preview_length:
                preview += "..."
            entry.metadata["prompt_preview"] = preview

        return entry

    def commit_entry(self, entry: AuditEntry) -> None:
        """Commit a completed entry to the audit log.

        Args:
            entry: Completed AuditEntry
        """
        if not self.config.enabled:
            return

        with self._lock:
            # Check for log rotation
            self._maybe_rotate()

            # Append to log file
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")

        logger.debug(f"Audit entry committed: {entry.id} ({entry.agent}/{entry.task_id})")

    @contextmanager
    def record(
        self,
        agent: str,
        task_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        command: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> Generator[AuditEntry, None, None]:
        """Context manager for recording an invocation.

        Automatically tracks timing and commits the entry.

        Usage:
            with trail.record("claude", "T1", prompt) as entry:
                result = run_command(...)
                entry.set_result(result.success, result.exit_code, ...)

        Args:
            agent: Agent identifier
            task_id: Task ID
            prompt: The prompt
            session_id: Session ID
            command: CLI command
            metadata: Additional metadata

        Yields:
            AuditEntry to track the invocation
        """
        entry = self.start_entry(
            agent=agent,
            task_id=task_id,
            prompt=prompt,
            session_id=session_id,
            command=command,
            metadata=metadata,
        )

        try:
            yield entry
        except Exception as e:
            entry.set_error(str(e))
            raise
        finally:
            self.commit_entry(entry)

    def _maybe_rotate(self) -> None:
        """Rotate log file if needed."""
        if not self.log_file.exists():
            return

        # Check file size
        size_mb = self.log_file.stat().st_size / (1024 * 1024)
        if size_mb < self.config.max_log_size_mb:
            return

        # Rotate: rename current file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated_name = f"invocations_{timestamp}.jsonl"
        rotated_path = self.audit_dir / rotated_name

        self.log_file.rename(rotated_path)
        logger.info(f"Rotated audit log to {rotated_name}")

        # Clean up old rotated files
        self._cleanup_old_logs()

    def _cleanup_old_logs(self) -> None:
        """Remove audit logs older than max_log_age_days."""
        cutoff = datetime.now() - timedelta(days=self.config.max_log_age_days)

        for log_file in self.audit_dir.glob("invocations_*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if mtime < cutoff:
                    log_file.unlink()
                    logger.info(f"Removed old audit log: {log_file.name}")
            except (OSError, ValueError) as e:
                logger.warning(f"Failed to clean up {log_file}: {e}")

    def query(
        self,
        task_id: Optional[str] = None,
        agent: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[AuditEntry]:
        """Query audit log entries.

        Args:
            task_id: Filter by task ID
            agent: Filter by agent
            status: Filter by status
            since: Filter entries after this time
            until: Filter entries before this time
            limit: Maximum number of entries to return

        Returns:
            List of matching AuditEntry objects
        """
        if not self.log_file.exists():
            return []

        entries = []

        for entry in self._iter_entries():
            # Apply filters
            if task_id and entry.task_id != task_id:
                continue
            if agent and entry.agent != agent:
                continue
            if status and entry.status != status:
                continue

            entry_time = datetime.fromisoformat(entry.timestamp)
            if since and entry_time < since:
                continue
            if until and entry_time > until:
                continue

            entries.append(entry)

            if limit and len(entries) >= limit:
                break

        return entries

    def _iter_entries(self) -> Iterator[AuditEntry]:
        """Iterate over all entries in the log file."""
        if not self.log_file.exists():
            return

        with open(self.log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    yield AuditEntry.from_dict(data)
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to parse audit entry: {e}")

    def get_task_history(self, task_id: str) -> list[AuditEntry]:
        """Get all invocations for a task.

        Args:
            task_id: Task identifier

        Returns:
            List of audit entries for the task, chronologically ordered
        """
        return sorted(
            self.query(task_id=task_id),
            key=lambda e: e.timestamp,
        )

    def get_statistics(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """Get summary statistics for audit log.

        Args:
            since: Start of time range
            until: End of time range

        Returns:
            Dictionary with statistics
        """
        entries = self.query(since=since, until=until)

        if not entries:
            return {
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
                "timeout_count": 0,
                "success_rate": 0.0,
                "total_cost_usd": 0.0,
                "total_duration_seconds": 0.0,
                "avg_duration_seconds": 0.0,
                "by_agent": {},
                "by_status": {},
            }

        success_count = sum(1 for e in entries if e.status == "success")
        failed_count = sum(1 for e in entries if e.status == "failed")
        timeout_count = sum(1 for e in entries if e.status == "timeout")

        total_cost = sum(e.cost_usd or 0 for e in entries)
        total_duration = sum(e.duration_seconds for e in entries)

        by_agent: dict[str, int] = {}
        by_status: dict[str, int] = {}

        for entry in entries:
            by_agent[entry.agent] = by_agent.get(entry.agent, 0) + 1
            by_status[entry.status] = by_status.get(entry.status, 0) + 1

        return {
            "total": len(entries),
            "success_count": success_count,
            "failed_count": failed_count,
            "timeout_count": timeout_count,
            "success_rate": success_count / len(entries) if entries else 0.0,
            "total_cost_usd": total_cost,
            "total_duration_seconds": total_duration,
            "avg_duration_seconds": total_duration / len(entries) if entries else 0.0,
            "by_agent": by_agent,
            "by_status": by_status,
        }

    def export_csv(self, output_path: Path) -> int:
        """Export audit log to CSV format.

        Args:
            output_path: Path to write CSV file

        Returns:
            Number of entries exported
        """
        import csv

        entries = list(self._iter_entries())
        if not entries:
            return 0

        # Define CSV columns
        fieldnames = [
            "id",
            "timestamp",
            "agent",
            "task_id",
            "session_id",
            "status",
            "exit_code",
            "duration_seconds",
            "prompt_length",
            "output_length",
            "cost_usd",
            "model",
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for entry in entries:
                row = {k: getattr(entry, k, None) for k in fieldnames}
                writer.writerow(row)

        return len(entries)


def create_audit_trail(
    project_dir: Path | str,
    config: Optional[AuditConfig] = None,
) -> AuditTrail:
    """Factory function to create an audit trail.

    Args:
        project_dir: Project directory
        config: Optional configuration

    Returns:
        Configured AuditTrail instance
    """
    return AuditTrail(project_dir, config)


# Cache of audit trails per project
_audit_trails: dict[str, AuditTrail] = {}
_trails_lock = threading.Lock()


def get_project_audit_trail(project_dir: Path | str) -> AuditTrail:
    """Get or create audit trail for a project.

    Caches audit trails to avoid creating multiple instances.

    Args:
        project_dir: Project directory

    Returns:
        AuditTrail for the project
    """
    key = str(Path(project_dir).resolve())

    with _trails_lock:
        if key not in _audit_trails:
            _audit_trails[key] = AuditTrail(project_dir)
        return _audit_trails[key]
