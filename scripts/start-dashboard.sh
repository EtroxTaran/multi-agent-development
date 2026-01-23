#!/bin/bash
# Start Conductor Dashboard (backend + frontend)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$ROOT_DIR/dashboard/backend"
FRONTEND_DIR="$ROOT_DIR/dashboard/frontend"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# PIDs for cleanup
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo -e "\n${YELLOW}Shutting down dashboard...${NC}"
    if [ -n "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    # Kill any remaining processes on the ports
    lsof -ti:8091 | xargs kill -9 2>/dev/null || true
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    echo -e "${GREEN}Dashboard stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}           Conductor Dashboard Launcher${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check if directories exist
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}Error: Backend directory not found at $BACKEND_DIR${NC}"
    exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}Error: Frontend directory not found at $FRONTEND_DIR${NC}"
    exit 1
fi

# Install backend dependencies if needed
echo -e "\n${YELLOW}[1/4] Checking backend dependencies...${NC}"
cd "$BACKEND_DIR"
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt 2>/dev/null || pip install -r requirements.txt

# Install frontend dependencies if needed
echo -e "${YELLOW}[2/4] Checking frontend dependencies...${NC}"
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    echo "Installing npm packages..."
    npm install
else
    echo "Node modules found."
fi

# Check Database
echo -e "${YELLOW}[0/4] Checking database...${NC}"
if ! curl -s http://localhost:8001/status > /dev/null; then
    echo "Starting SurrealDB..."
    # Try to start existing container, or run new one
    docker start conductor-surrealdb 2>/dev/null || \
    docker run -d --name conductor-surrealdb -p 8001:8000 -v conductor_surrealdb-data:/data --user 0:0 surrealdb/surrealdb:v2.1.4 start --user root --pass root rocksdb:/data/conductor.db

    # Wait for DB
    echo -n "Waiting for database"
    for i in {1..10}; do
        if curl -s http://localhost:8001/status > /dev/null; then
            echo -e " ${GREEN}ready!${NC}"
            break
        fi
        echo -n "."
        sleep 1
    done
else
    echo "Database is running."
fi

# Start backend
echo -e "${YELLOW}[3/4] Starting backend server...${NC}"
export PYTHONPATH=$ROOT_DIR:$PYTHONPATH
cd "$BACKEND_DIR"
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8091 --reload > /tmp/conductor-backend.log 2>&1 &
BACKEND_PID=$!

# Wait for backend to be ready
echo -n "Waiting for backend"
for i in {1..30}; do
    if curl -s http://localhost:8091/health > /dev/null 2>&1; then
        echo -e " ${GREEN}ready!${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# Start frontend
echo -e "${YELLOW}[4/4] Starting frontend server...${NC}"
cd "$FRONTEND_DIR"
npm run dev > /tmp/conductor-frontend.log 2>&1 &
FRONTEND_PID=$!

# Wait for frontend to be ready
echo -n "Waiting for frontend"
for i in {1..30}; do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo -e " ${GREEN}ready!${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Dashboard is running!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${GREEN}➜${NC}  Dashboard:  ${BLUE}http://localhost:3000${NC}"
echo -e "  ${GREEN}➜${NC}  API:        ${BLUE}http://localhost:8091${NC}"
echo -e "  ${GREEN}➜${NC}  API Docs:   ${BLUE}http://localhost:8091/docs${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the dashboard${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Keep script running and show logs
tail -f /tmp/conductor-backend.log /tmp/conductor-frontend.log 2>/dev/null &
wait
