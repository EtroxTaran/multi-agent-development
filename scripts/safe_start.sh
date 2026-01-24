#!/bin/bash
# scripts/safe_start.sh
# Wrapper to run orchestrator commands safely, capturing all output for the Watchdog.

PROJECT_DIR=${2:-"."}
if [[ "$*" == *"--project "* ]]; then
    # Extract project name if passed
    # This is a bit rough, but sufficient for now
    PROJECT_NAME=$(echo "$*" | sed -n 's/.*--project \([^ ]*\).*/\1/p')
    if [ -n "$PROJECT_NAME" ]; then
        PROJECT_DIR="projects/$PROJECT_NAME"
    fi
fi

WORKFLOW_DIR="$PROJECT_DIR/.workflow"
ERRORS_DIR="$WORKFLOW_DIR/errors"
LOG_FILE="$ERRORS_DIR/startup.log"

# Ensure error directory exists
mkdir -p "$ERRORS_DIR"

# Start Watchdog if not running (placeholder logic)
# In a real system, we'd check for a pid file or process.
# For now, we assume this script *is* the way we run things, so it handles logging.

echo "Timestamp: $(date -Iseconds)" >> "$LOG_FILE"
echo "Command: $@" >> "$LOG_FILE"

# Run command and redirect stderr + stdout to log file AND console (tee)
# We append to the log file so we don't lose history.
"$@" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

if [ $EXIT_CODE -ne 0 ]; then
    echo "Command failed with exit code $EXIT_CODE" | tee -a "$LOG_FILE"
    # Explicitly signal failure to the logs in a format Watchdog will definitely see if it's tailoring tailing it
    echo "{\"level\": \"ERROR\", \"message\": \"Command failed with exit code $EXIT_CODE\", \"exit_code\": $EXIT_CODE, \"timestamp\": \"$(date -Iseconds)\"}" >> "$ERRORS_DIR/startup_errors.jsonl"
fi

exit $EXIT_CODE
