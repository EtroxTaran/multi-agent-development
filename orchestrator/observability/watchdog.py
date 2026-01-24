import asyncio
import json
from pathlib import Path

from orchestrator.fixer.agent import FixerAgent
from orchestrator.fixer.triage import FixerError
from orchestrator.utils.logging import LogLevel, OrchestrationLogger


class RuntimeWatchdog:
    """
    Monitors application error logs and triggers self-healing via FixerAgent.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.workflow_dir = project_dir / ".workflow"
        self.errors_dir = self.workflow_dir / "errors"

        # Ensure directories exist
        self.errors_dir.mkdir(parents=True, exist_ok=True)

        # Logger setup
        self.logger = OrchestrationLogger(
            workflow_dir=self.workflow_dir, console_output=True, min_level=LogLevel.INFO
        )

        self.fixer = FixerAgent(project_dir)

        # State tracking: file path -> last read byte offset
        self.file_offsets: dict[Path, int] = {}
        # Keep track of known files to detect new ones
        self.known_files: set[Path] = set()

    async def start(self, poll_interval: float = 2.0):
        """Starts the monitoring loop."""
        self.logger.info("Runtime Watchdog started. Monitoring for errors...")

        while True:
            try:
                await self.check_logs()
            except Exception as e:
                self.logger.error(f"Watchdog loop error: {e}")

            await asyncio.sleep(poll_interval)

    async def check_logs(self):
        """Checks for new log files and new content in existing files."""
        current_files = set(self.errors_dir.glob("*.jsonl"))

        # Initialize offsets for new files (start at end to avoid re-processing old errors on restart)
        # Note: If we want to process ALL errors on startup, set to 0.
        # For a "Watchdog", catching up on missed errors is usually good,
        # but avoiding "fix loops" on old errors is also important.
        # Let's start at 0 but maybe the FixerAgent dedupes?
        # FixerAgent has fix_history, but re-triggering might be noisy.
        # Let's default to 0 (process everything) for now, relying on Fixer to be smart.
        new_files = current_files - self.known_files
        for f in new_files:
            self.logger.info(f"New log file detected: {f.name}")
            # If the file is huge, maybe seek to end?
            # For now, start from beginning.
            self.file_offsets[f] = 0
            self.known_files.add(f)

        # Check for new content
        for log_file in current_files:
            await self._process_file(log_file)

    async def _process_file(self, log_file: Path):
        """Reads new lines from a log file and triggers fixes."""
        try:
            current_offset = self.file_offsets.get(log_file, 0)

            if not log_file.exists():
                return

            # Check size to see if it grew
            file_size = log_file.stat().st_size
            if file_size < current_offset:
                # File was truncated/rotated
                current_offset = 0

            if file_size == current_offset:
                return

            async with asyncio.Lock():  # Simple lock if we were concurrent, but we are single looped here.
                with open(log_file, encoding="utf-8") as f:
                    f.seek(current_offset)

                    lines = f.readlines()
                    self.file_offsets[log_file] = f.tell()

            for line in lines:
                await self._handle_log_line(line.strip())

        except Exception as e:
            self.logger.error(f"Error reading {log_file.name}: {e}")

    async def _handle_log_line(self, line: str):
        """Parses a log line and attempts a fix if it's an error."""
        if not line:
            return

        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # Not a JSONL line, treat as raw log line
            # Check for common error patterns
            if "Traceback" in line or "Error:" in line or "Exception" in line:
                entry = {"level": "ERROR", "message": line.strip(), "error_type": "RawLogError"}
            else:
                return

        # We expect specific fields.
        # Check if it looks like an error we define or just a generic log
        # LogManager might write various JSONL.
        # We assume errors.jsonl contains error objects.

        # Basic validation: needs 'level'='ERROR' or 'message' or 'stack_trace'
        if entry.get("level") != "ERROR" and "error" not in entry and "stack_trace" not in entry:
            return

        self.logger.info(f"Error detected: {entry.get('message', 'Unknown Error')[:50]}...")

        # Construct FixerError
        # Assuming the log structure matches what Fixer expects or we map it.
        # FixerError expects: error_type, error_message, stack_trace, file_path, line_number (all optional-ish)

        fixer_error = FixerError(
            error_type=entry.get("error_type", "RuntimeError"),
            error_message=entry.get("message") or entry.get("error", "Unknown error"),
            stack_trace=entry.get("stack_trace") or entry.get("traceback"),
            file_path=entry.get("file_path"),
            line_number=entry.get("line_number"),
        )

        try:
            self.logger.info("Triggering FixerAgent...")
            # We don't have a specific Workflow State here, pass None or empty.
            result = await self.fixer.attempt_fix(fixer_error)

            if result.success:
                self.logger.info(f"Fix applied successfully: {result.fix_description}")
            else:
                self.logger.warning(f"Fix attempt failed: {result.error_message}")

        except Exception as e:
            self.logger.error(f"Failed to trigger FixerAgent: {e}")
