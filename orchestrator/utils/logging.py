"""Logging utilities for the orchestration workflow."""

import json
import re
import sys
import threading
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class LogLevel(str, Enum):
    """Log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"
    PHASE = "PHASE"
    AGENT = "AGENT"


# ANSI color codes
COLORS = {
    LogLevel.DEBUG: "\033[90m",  # Gray
    LogLevel.INFO: "\033[37m",  # White
    LogLevel.WARNING: "\033[93m",  # Yellow
    LogLevel.ERROR: "\033[91m",  # Red
    LogLevel.SUCCESS: "\033[92m",  # Green
    LogLevel.PHASE: "\033[96m",  # Cyan
    LogLevel.AGENT: "\033[95m",  # Magenta
}
RESET = "\033[0m"
BOLD = "\033[1m"


class SecretsRedactor:
    """Redact secrets from log messages.

    Automatically detects and redacts sensitive information like
    API keys, passwords, tokens, and bearer tokens from log output.
    """

    PATTERNS = [
        # OpenAI/Anthropic style API keys (must come first to catch before generic patterns)
        (r"\bsk-[a-zA-Z0-9]{10,}", "***API_KEY_REDACTED***"),
        # GitHub tokens (classic and fine-grained)
        # ghp_ = personal access tokens, ghu_ = user-to-server, gho_ = OAuth
        # ghs_ = server-to-server, ghr_ = refresh tokens
        (r"\b(ghp_[a-zA-Z0-9]{36,})", "***GITHUB_PAT_REDACTED***"),
        (r"\b(ghu_[a-zA-Z0-9]{36,})", "***GITHUB_USER_TOKEN_REDACTED***"),
        (r"\b(gho_[a-zA-Z0-9]{36,})", "***GITHUB_OAUTH_REDACTED***"),
        (r"\b(ghs_[a-zA-Z0-9]{36,})", "***GITHUB_SERVER_TOKEN_REDACTED***"),
        (r"\b(ghr_[a-zA-Z0-9]{36,})", "***GITHUB_REFRESH_TOKEN_REDACTED***"),
        # GitHub App tokens
        (r"\b(github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59})", "***GITHUB_PAT_REDACTED***"),
        # AWS credentials (comprehensive patterns)
        (
            r'(?i)(AWS_SECRET_ACCESS_KEY)["\s:=]+["\']?([a-zA-Z0-9/+]{40})["\']?',
            r"\1=***REDACTED***",
        ),
        (r'(?i)(AWS_ACCESS_KEY_ID)["\s:=]+["\']?([A-Z0-9]{20})["\']?', r"\1=***REDACTED***"),
        (r"\b(AKIA[0-9A-Z]{16})", "***AWS_KEY_REDACTED***"),
        # Google Cloud / Firebase
        (
            r'(?i)(GOOGLE_API_KEY|FIREBASE_API_KEY)["\s:=]+["\']?([a-zA-Z0-9_\-]{20,})["\']?',
            r"\1=***REDACTED***",
        ),
        (r"\bAIza[0-9A-Za-z\-_]{35}", "***GOOGLE_API_KEY_REDACTED***"),
        # API keys (various formats)
        (
            r'(?i)(api[_-]?key|apikey)["\s:=]+["\']?([a-zA-Z0-9_\-]{20,})["\']?',
            r"\1=***REDACTED***",
        ),
        # Passwords
        (r'(?i)(password|passwd|pwd)["\s:=]+["\']?([^\s"\']+)["\']?', r"\1=***REDACTED***"),
        # Secrets and tokens
        (r'(?i)(secret|token)["\s:=]+["\']?([a-zA-Z0-9_\-]{10,})["\']?', r"\1=***REDACTED***"),
        # Bearer tokens
        (r"(?i)(bearer\s+)([a-zA-Z0-9_\-\.]+)", r"\1***REDACTED***"),
        # AWS-style credentials (legacy pattern, kept for compatibility)
        (
            r'(?i)(aws[_-]?(?:access[_-]?key|secret)[_-]?(?:id)?)["\s:=]+["\']?([A-Z0-9]{16,})["\']?',
            r"\1=***REDACTED***",
        ),
        # Slack tokens
        (r"\b(xox[baprs]-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24})", "***SLACK_TOKEN_REDACTED***"),
        # Generic private key patterns
        (
            r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC )?PRIVATE KEY-----",
            "***PRIVATE_KEY_REDACTED***",
        ),
    ]

    def __init__(self):
        """Initialize with compiled patterns."""
        self._compiled_patterns = [
            (re.compile(pattern), replacement) for pattern, replacement in self.PATTERNS
        ]

    def redact(self, message: str) -> str:
        """Redact sensitive information from message.

        Args:
            message: The log message that may contain secrets

        Returns:
            The message with secrets redacted
        """
        for pattern, replacement in self._compiled_patterns:
            message = pattern.sub(replacement, message)
        return message


class OrchestrationLogger:
    """Logger for multi-agent orchestration.

    Thread-safe logging with automatic secrets redaction.
    Outputs to console, plain text file, and JSON lines file.
    Optionally forwards events to a Rich UI display.
    """

    # Default rotation settings
    DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    DEFAULT_MAX_BACKUP_COUNT = 5
    ROTATION_CHECK_INTERVAL = 100  # Check every N log writes

    def __init__(
        self,
        workflow_dir: str | Path,
        console_output: bool = True,
        min_level: LogLevel = LogLevel.INFO,
        redact_secrets: bool = True,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_backup_count: int = DEFAULT_MAX_BACKUP_COUNT,
    ):
        """Initialize the logger.

        Args:
            workflow_dir: Directory for log files
            console_output: Whether to print to console
            min_level: Minimum log level to record
            redact_secrets: Whether to redact secrets from logs
            max_file_size: Maximum log file size in bytes before rotation (default 10MB)
            max_backup_count: Number of backup files to keep (default 5)
        """
        self.workflow_dir = Path(workflow_dir)
        self.log_file = self.workflow_dir / "coordination.log"
        self.json_log_file = self.workflow_dir / "coordination.jsonl"
        self.console_output = console_output
        self.min_level = min_level
        self.max_file_size = max_file_size
        self.max_backup_count = max_backup_count
        self._log_lock = threading.Lock()
        self._redactor = SecretsRedactor() if redact_secrets else None
        self._ui_display = None  # Optional Rich UI display
        self._write_count = 0  # Track writes for rotation check
        self._ensure_log_dir()
        # Keep file handles open to avoid descriptor exhaustion
        # Use line buffering (buffering=1) for immediate writes
        self._log_handle = open(self.log_file, "a", encoding="utf-8", buffering=1)
        self._json_handle = open(self.json_log_file, "a", encoding="utf-8", buffering=1)
        self._closed = False

    def __del__(self):
        """Close file handles on destruction."""
        self.close()

    def close(self):
        """Close log file handles."""
        if self._closed:
            return
        self._closed = True
        try:
            if hasattr(self, "_log_handle") and self._log_handle:
                self._log_handle.close()
            if hasattr(self, "_json_handle") and self._json_handle:
                self._json_handle.close()
        except Exception:
            pass  # Ignore errors during cleanup

    def _rotate_file(self, file_path: Path, file_handle) -> any:
        """Rotate a log file if it exceeds max size.

        Args:
            file_path: Path to the log file
            file_handle: Current file handle

        Returns:
            New file handle (or same handle if no rotation needed)
        """
        try:
            # Check file size
            if not file_path.exists():
                return file_handle

            file_size = file_path.stat().st_size
            if file_size < self.max_file_size:
                return file_handle

            # Close current handle
            file_handle.close()

            # Rotate existing backups (e.g., .log.4 -> .log.5, .log.3 -> .log.4, ...)
            for i in range(self.max_backup_count - 1, 0, -1):
                src = Path(f"{file_path}.{i}")
                dst = Path(f"{file_path}.{i + 1}")
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    src.rename(dst)

            # Rotate current file to .1
            backup_path = Path(f"{file_path}.1")
            if backup_path.exists():
                backup_path.unlink()
            file_path.rename(backup_path)

            # Open new file
            return open(file_path, "a", encoding="utf-8", buffering=1)

        except Exception:
            # If rotation fails, try to reopen the file
            try:
                return open(file_path, "a", encoding="utf-8", buffering=1)
            except Exception:
                return file_handle

    def _check_rotation(self) -> None:
        """Check and perform log rotation if needed.

        Called periodically (every ROTATION_CHECK_INTERVAL writes) to avoid
        checking file size on every log call.
        """
        self._write_count += 1
        if self._write_count < self.ROTATION_CHECK_INTERVAL:
            return

        self._write_count = 0

        # Rotate text log
        if self._log_handle and not self._closed:
            self._log_handle = self._rotate_file(self.log_file, self._log_handle)

        # Rotate JSON log
        if self._json_handle and not self._closed:
            self._json_handle = self._rotate_file(self.json_log_file, self._json_handle)

    def set_ui_display(self, display) -> None:
        """Set a UI display to forward log events to.

        When set, log events will be forwarded to the display's
        log_event method in addition to normal logging.

        Args:
            display: Display object with log_event(message, level) method
        """
        self._ui_display = display

    def clear_ui_display(self) -> None:
        """Clear the UI display reference."""
        self._ui_display = None

    def _ensure_log_dir(self) -> None:
        """Ensure log directory exists."""
        self.workflow_dir.mkdir(parents=True, exist_ok=True)

    def _get_level_priority(self, level: LogLevel) -> int:
        """Get numeric priority for log level."""
        priorities = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.SUCCESS: 1,
            LogLevel.PHASE: 1,
            LogLevel.AGENT: 1,
        }
        return priorities.get(level, 1)

    def _should_log(self, level: LogLevel) -> bool:
        """Check if message should be logged based on level."""
        return self._get_level_priority(level) >= self._get_level_priority(self.min_level)

    def _format_console(
        self,
        level: LogLevel,
        message: str,
        phase: Optional[int] = None,
        agent: Optional[str] = None,
    ) -> str:
        """Format message for console output with colors."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = COLORS.get(level, "")

        parts = [f"{COLORS[LogLevel.DEBUG]}[{timestamp}]{RESET}"]

        if phase is not None:
            parts.append(f"{COLORS[LogLevel.PHASE]}[P{phase}]{RESET}")

        if agent:
            parts.append(f"{COLORS[LogLevel.AGENT]}[{agent}]{RESET}")

        parts.append(f"{color}[{level.value}]{RESET}")
        parts.append(message)

        return " ".join(parts)

    def _format_file(
        self,
        level: LogLevel,
        message: str,
        phase: Optional[int] = None,
        agent: Optional[str] = None,
    ) -> str:
        """Format message for file output (plain text)."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"[{timestamp}]"]

        if phase is not None:
            parts.append(f"[P{phase}]")

        if agent:
            parts.append(f"[{agent}]")

        parts.append(f"[{level.value}]")
        parts.append(message)

        return " ".join(parts)

    def _format_json(
        self,
        level: LogLevel,
        message: str,
        phase: Optional[int] = None,
        agent: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> dict:
        """Format message as JSON."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "message": message,
        }

        if phase is not None:
            entry["phase"] = phase

        if agent:
            entry["agent"] = agent

        if extra:
            entry["extra"] = extra

        return entry

    def log(
        self,
        level: LogLevel,
        message: str,
        phase: Optional[int] = None,
        agent: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """Log a message (thread-safe).

        Args:
            level: Log level
            message: Message to log
            phase: Phase number (1-5)
            agent: Agent name (claude, cursor, gemini)
            extra: Additional structured data
        """
        if not self._should_log(level):
            return

        # Redact secrets from message if enabled
        if self._redactor:
            message = self._redactor.redact(message)
            # Also redact from extra data if present
            if extra:
                extra = self._redact_dict(extra)

        with self._log_lock:
            # Console output
            if self.console_output:
                formatted = self._format_console(level, message, phase, agent)
                print(formatted, file=sys.stderr if level == LogLevel.ERROR else sys.stdout)

            # File output (plain text) - use cached handle
            if not self._closed and self._log_handle:
                formatted = self._format_file(level, message, phase, agent)
                self._log_handle.write(formatted + "\n")

            # JSON log - use cached handle
            if not self._closed and self._json_handle:
                entry = self._format_json(level, message, phase, agent, extra)
                self._json_handle.write(json.dumps(entry) + "\n")

            # Forward to UI display if set
            if self._ui_display:
                try:
                    ui_level = self._map_level_to_ui(level)
                    display_message = message
                    if agent:
                        display_message = f"[{agent}] {message}"
                    self._ui_display.log_event(display_message, ui_level)
                except Exception:
                    pass  # Don't let UI errors affect logging

            # Check for log rotation periodically
            self._check_rotation()

    def _map_level_to_ui(self, level: LogLevel) -> str:
        """Map internal log level to UI display level.

        Args:
            level: Internal log level

        Returns:
            UI level string (info, warning, error, success)
        """
        mapping = {
            LogLevel.DEBUG: "info",
            LogLevel.INFO: "info",
            LogLevel.WARNING: "warning",
            LogLevel.ERROR: "error",
            LogLevel.SUCCESS: "success",
            LogLevel.PHASE: "info",
            LogLevel.AGENT: "info",
        }
        return mapping.get(level, "info")

    def _redact_dict(self, data: dict) -> dict:
        """Recursively redact secrets from a dictionary."""
        if not self._redactor:
            return data

        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self._redactor.redact(value)
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self._redact_dict(item)
                    if isinstance(item, dict)
                    else self._redactor.redact(item)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.log(LogLevel.ERROR, message, **kwargs)

    def success(self, message: str, **kwargs) -> None:
        """Log success message."""
        self.log(LogLevel.SUCCESS, message, **kwargs)

    def phase_start(self, phase_num: int, phase_name: str) -> None:
        """Log phase start."""
        self.log(
            LogLevel.PHASE,
            f"{'='*50}",
        )
        self.log(
            LogLevel.PHASE,
            f"Starting Phase {phase_num}: {phase_name.upper()}",
            phase=phase_num,
        )
        self.log(
            LogLevel.PHASE,
            f"{'='*50}",
        )

    def phase_complete(self, phase_num: int, phase_name: str) -> None:
        """Log phase completion."""
        self.log(
            LogLevel.SUCCESS,
            f"Phase {phase_num} ({phase_name}) completed successfully",
            phase=phase_num,
        )

    def phase_failed(self, phase_num: int, phase_name: str, error: str) -> None:
        """Log phase failure."""
        self.log(
            LogLevel.ERROR,
            f"Phase {phase_num} ({phase_name}) failed: {error}",
            phase=phase_num,
        )

    def agent_start(self, agent: str, task: str, phase: Optional[int] = None) -> None:
        """Log agent task start."""
        self.log(
            LogLevel.AGENT,
            f"Agent starting: {task}",
            phase=phase,
            agent=agent,
        )

    def agent_complete(self, agent: str, task: str, phase: Optional[int] = None) -> None:
        """Log agent task completion."""
        self.log(
            LogLevel.SUCCESS,
            f"Agent completed: {task}",
            phase=phase,
            agent=agent,
        )

    def agent_error(self, agent: str, error: str, phase: Optional[int] = None) -> None:
        """Log agent error."""
        self.log(
            LogLevel.ERROR,
            f"Agent error: {error}",
            phase=phase,
            agent=agent,
        )

    def retry(self, phase_num: int, attempt: int, max_attempts: int) -> None:
        """Log retry attempt."""
        self.log(
            LogLevel.WARNING,
            f"Retrying phase (attempt {attempt}/{max_attempts})",
            phase=phase_num,
        )

    def commit(self, phase_num: int, commit_hash: str, message: str) -> None:
        """Log git commit."""
        self.log(
            LogLevel.SUCCESS,
            f"Committed: {commit_hash[:8]} - {message}",
            phase=phase_num,
            extra={"commit_hash": commit_hash, "commit_message": message},
        )

    def separator(self) -> None:
        """Print a visual separator."""
        if self.console_output:
            print("-" * 60)

    def banner(self, text: str) -> None:
        """Print a banner message."""
        if self.console_output:
            print()
            print(f"{BOLD}{COLORS[LogLevel.PHASE]}{'='*60}{RESET}")
            print(f"{BOLD}{COLORS[LogLevel.PHASE]}{text.center(60)}{RESET}")
            print(f"{BOLD}{COLORS[LogLevel.PHASE]}{'='*60}{RESET}")
            print()
