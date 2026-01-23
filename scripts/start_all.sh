#!/bin/bash
# Start all Conductor services: Dashboard, API, and Watchdog.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down all services...${NC}"
    # The dashboard script handles its own cleanup (backend+frontend)
    # We just need to kill the processes we started directly
    if [ -n "$WATCHDOG_PID" ]; then
        kill "$WATCHDOG_PID" 2>/dev/null || true
    fi
    # Dashboard script usually traps cleaning up its children, but we are running it.
    # Since we are running start-dashboard.sh in foreground typically?
    # Let's run dashboard in background to allow watchdog to run?
    # Or start watchdog in background.

    # If we started dashboard in background, kill it
    if [ -n "$DASHBOARD_PID" ]; then
        kill "$DASHBOARD_PID" 2>/dev/null || true
    fi

    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}           Conductor System Launcher${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check prerequisites (simple check)
if [ ! -f "$ROOT_DIR/uv.lock" ] && [ ! -d "$ROOT_DIR/.venv" ]; then
    echo -e "${YELLOW}First run detected? Installing dependencies...${NC}"
    if command -v uv &> /dev/null; then
        uv sync
    else
        echo -e "${RED}uv not installed. Please install uv or run setup manually.${NC}"
    fi
fi

# 1. Start Watchdog in background
echo -e "${YELLOW}[1/2] Starting Runtime Watchdog...${NC}"
# Use uv run to ensure we use the project environment
uv run "$SCRIPT_DIR/start_watchdog.py" > /tmp/conductor-watchdog.log 2>&1 &
WATCHDOG_PID=$!
echo -e "${GREEN}Watchdog started (PID $WATCHDOG_PID). Logs: /tmp/conductor-watchdog.log${NC}"

# 2. Start Dashboard (which starts Backend + Frontend + DB check)
echo -e "${YELLOW}[2/2] Starting Dashboard...${NC}"
"$SCRIPT_DIR/start-dashboard.sh" &
DASHBOARD_PID=$!

# Wait for both
wait
