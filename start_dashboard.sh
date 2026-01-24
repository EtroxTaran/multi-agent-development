#!/bin/bash

# Kill existing processes on ports 8091 and 3000
fuser -k 8091/tcp
fuser -k 3000/tcp

# Export PYTHONPATH to include the project root
export PYTHONPATH=/home/etrox/workspace/conductor

# Start Backend
cd /home/etrox/workspace/conductor/dashboard/backend
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8091 > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID $BACKEND_PID"

# Start Frontend
cd /home/etrox/workspace/conductor/dashboard/frontend
nohup npm run dev -- --port 3000 --host > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started with PID $FRONTEND_PID"

echo "Waiting for services to start..."
sleep 5
