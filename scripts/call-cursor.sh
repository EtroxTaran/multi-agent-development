#!/bin/bash
# call-cursor.sh - Invoke Cursor CLI for code review/validation
# Usage: call-cursor.sh <prompt-file> <output-file> [project-dir]
#
# This script is used by Claude Code to call Cursor for:
# - Plan validation (Phase 2)
# - Code verification (Phase 4)
#
# Default model: GPT-5.2-Codex (latest as of Jan 2026)
# Can be overridden with CURSOR_MODEL environment variable

set -e

PROMPT_FILE="$1"
OUTPUT_FILE="$2"
PROJECT_DIR="${3:-.}"

# Resolve to absolute path
PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)

# Model selection (GPT-5.2-Codex is the latest, most capable coding model)
# Options: gpt-5.2-codex, gpt-5.1-codex, gpt-4.5-turbo, claude-sonnet-4
CURSOR_MODEL="${CURSOR_MODEL:-gpt-5.2-codex}"

# Validate arguments
if [ -z "$PROMPT_FILE" ] || [ -z "$OUTPUT_FILE" ]; then
    echo "Usage: call-cursor.sh <prompt-file> <output-file> [project-dir]"
    echo ""
    echo "Environment variables:"
    echo "  CURSOR_MODEL - Model to use (default: gpt-5.2-codex)"
    echo "                 Options: gpt-5.2-codex, gpt-5.1-codex, gpt-4.5-turbo"
    exit 1
fi

if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: Prompt file not found: $PROMPT_FILE"
    exit 1
fi

# Change to project directory
cd "$PROJECT_DIR"

# Check if cursor-agent is available
if ! command -v cursor-agent &> /dev/null; then
    echo '{"status": "error", "agent": "cursor", "message": "cursor-agent CLI not found. Please install it."}' > "$OUTPUT_FILE"
    exit 1
fi

# Read prompt from file
PROMPT=$(cat "$PROMPT_FILE")

# Build context file options
# Cursor reads .cursor/rules automatically, but we can also specify AGENTS.md
CONTEXT_OPTS=""
if [ -f "AGENTS.md" ]; then
    CONTEXT_OPTS="--read AGENTS.md"
fi

# Call Cursor CLI with JSON output
# Note: cursor-agent CLI usage:
# - --print: Non-interactive mode (required for automation)
# - --output-format json: Output as JSON
# - --force: Force execution without confirmation
# - Model is configured via environment or config, not CLI flag
# - Prompt is a positional argument at the end
echo "Calling Cursor CLI..."

cursor-agent --print \
    --output-format json \
    --force \
    $CONTEXT_OPTS \
    "$PROMPT" \
    > "$OUTPUT_FILE" 2>&1

# Check if output was created
if [ ! -f "$OUTPUT_FILE" ]; then
    echo '{"status": "error", "agent": "cursor", "message": "Failed to create output file"}' > "$OUTPUT_FILE"
    exit 1
fi

# Validate JSON output
if ! python3 -c "import json; json.load(open('$OUTPUT_FILE'))" 2>/dev/null; then
    # If not valid JSON, wrap the output
    CONTENT=$(cat "$OUTPUT_FILE")
    echo "{\"status\": \"completed\", \"agent\": \"cursor\", \"raw_output\": $(echo "$CONTENT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}" > "$OUTPUT_FILE"
fi

echo "Cursor review complete. Output saved to: $OUTPUT_FILE"
