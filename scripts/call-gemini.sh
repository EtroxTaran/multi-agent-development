#!/bin/bash
# call-gemini.sh - Invoke Gemini CLI for architecture review/validation
# Usage: call-gemini.sh <prompt-file> <output-file> [project-dir]
#
# This script is used by Claude Code to call Gemini for:
# - Plan validation (Phase 2)
# - Architecture verification (Phase 4)
#
# Default model: Gemini 3 Pro (latest as of Jan 2026)
# Can be overridden with GEMINI_MODEL environment variable

set -e

PROMPT_FILE="$1"
OUTPUT_FILE="$2"
PROJECT_DIR="${3:-.}"

# Resolve to absolute path
PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd)

# Model selection (Gemini 3 Pro is the latest, most capable model)
# Options: gemini-3-pro, gemini-3-flash
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3-pro}"

# Validate arguments
if [ -z "$PROMPT_FILE" ] || [ -z "$OUTPUT_FILE" ]; then
    echo "Usage: call-gemini.sh <prompt-file> <output-file> [project-dir]"
    echo ""
    echo "Environment variables:"
    echo "  GEMINI_MODEL - Model to use (default: gemini-3-pro)"
    echo "                 Options: gemini-3-pro, gemini-3-flash"
    exit 1
fi

if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: Prompt file not found: $PROMPT_FILE"
    exit 1
fi

# Change to project directory
cd "$PROJECT_DIR"

# Check if gemini CLI is available
if ! command -v gemini &> /dev/null; then
    echo '{"status": "error", "agent": "gemini", "message": "gemini CLI not found. Install with: npm install -g @google/gemini-cli"}' > "$OUTPUT_FILE"
    exit 1
fi

# Read prompt from file
PROMPT=$(cat "$PROMPT_FILE")

# Build context file options
# Gemini CLI reads GEMINI.md automatically, but we can also specify AGENTS.md
CONTEXT_OPTS=""
if [ -f "AGENTS.md" ]; then
    CONTEXT_OPTS="--read AGENTS.md"
fi

# Call Gemini CLI
# Note: gemini CLI usage:
# - --yolo: Auto-approve tool calls (required for non-interactive mode)
# - Prompt is a positional argument
# - Gemini CLI does NOT support --output-format flag
# - Model can be set via GEMINI_MODEL env var or --model flag
echo "Calling Gemini CLI with model: $GEMINI_MODEL"

# Create temp file for raw output
TEMP_OUTPUT=$(mktemp)
trap "rm -f $TEMP_OUTPUT" EXIT

# Run Gemini CLI (note: no --output-format flag available)
run_gemini() {
    gemini --model "$GEMINI_MODEL" \
        --yolo \
        "$PROMPT" \
        > "$TEMP_OUTPUT" 2>&1
}

run_gemini

# Check for rate limits and fallback to Claude if needed
if grep -i -qE "rate limit|429|quota|too many requests|resource exhausted" "$TEMP_OUTPUT"; then
    echo "Warning: Gemini rate limit/quota detected"

    if command -v claude &> /dev/null; then
        echo "Falling back to Claude CLI (second best option)..."

        # Claude fallback - use Opus for best quality
        # Note: We use the same prompt file content
        claude -p "$PROMPT" \
            --output-format json \
            --fallback-model claude-4-5-opus \
            > "$TEMP_OUTPUT" 2>&1

        if [ $? -eq 0 ]; then
            echo "Fallback to Claude successful"
        else
            echo "Fallback to Claude failed"
        fi
    else
        echo "Claude CLI not available for fallback"
    fi
fi

# Check if output is valid JSON, if not wrap it - use env vars to avoid shell injection
export _TEMP_OUTPUT="$TEMP_OUTPUT"
export _OUTPUT_FILE="$OUTPUT_FILE"

if python3 -c "
import json
import os
import sys
try:
    with open(os.environ['_TEMP_OUTPUT']) as f:
        json.load(f)
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null; then
    # Already valid JSON, copy as-is
    cp "$TEMP_OUTPUT" "$OUTPUT_FILE"
else
    # Wrap raw output in JSON structure safely using env vars
    python3 <<'WRAP_SCRIPT'
import json
import os
import sys

temp_output = os.environ.get('_TEMP_OUTPUT')
output_file = os.environ.get('_OUTPUT_FILE')

if not temp_output or not output_file:
    sys.stderr.write("Error: Required env vars not set\n")
    sys.exit(1)

try:
    with open(temp_output, 'r') as f:
        content = f.read()
    wrapped = {
        "status": "completed",
        "agent": "gemini",
        "raw_output": content
    }
    with open(output_file, 'w') as f:
        json.dump(wrapped, f)
except Exception as e:
    sys.stderr.write(f"Error wrapping output: {e}\n")
    sys.exit(1)
WRAP_SCRIPT
fi

unset _TEMP_OUTPUT _OUTPUT_FILE

echo "Gemini review complete. Output saved to: $OUTPUT_FILE"
