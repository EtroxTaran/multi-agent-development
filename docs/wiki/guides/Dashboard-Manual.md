# Conductor Dashboard Guide

While the CLI is powerful, the **Conductor Dashboard** is where you see the matrix.

It provides a real-time, visual control center for monitoring your AI agents, tracking costs, and intervening when things go wrong.

---

## 🖥️ Launching the Dashboard

The dashboard is composed of a generic React frontend and a Python/FastAPI backend.

### One-Click Start
Run the helper script from the root of your repo:
```bash
./scripts/start-dashboard.sh
```

Wait until you see:
> ➜ Dashboard: http://localhost:3000

Open that URL in your browser.

---

## 📊 The Interface

### 1. The Header: Health & Status
At the very top, you see the vital signs of the project:
*   **Project Name**: The active workspace.
*   **Status Badge**: `In Progress` (Blue), `Paused` (Yellow), `Completed` (Green).
*   **Live Indicator**: Shows if the WebSocket connection to the Orchestrator is active.

### 2. The Graphs & Stats
*   **Task Progress**: A simple circular progress bar (e.g., "7/10 Tasks Completed").
*   **Current Phase**: Which of the 5 phases are we in? (Planning -> Validation -> Implementation -> Verification -> Completion).
*   **Agent Health**: Are all 3 CLI tools (Claude, Cursor, Gemini) online and responding?
*   **Cost**: Real-time spending on API tokens.

### 3. The Tabs

#### A. Graph View 🕸️
A visual node-graph (powered by LangGraph serialization).
*   **Blue Node**: Currently active.
*   **Green Node**: Completed successfully.
*   **Red Node**: Failed/Error.
*   *Click on any node to inspect the inputs/outputs passed to that agent.*

#### B. Task Board 📋
A Kanban-style view of your `PRODUCT.md` breakdown.
*   **Pending**: Tasks waiting for dependencies.
*   **In Progress**: Tasks currently being coded.
*   **Review**: Tasks waiting for 4-Eyes verification.
*   **Done**: Merged code.

#### C. Agent Feed 🤖
A live terminal stream of the agents "thinking".
*   You will see: `A04 (Claude) -> "Writing test for auth.py..."`
*   You will see: `A07 (Cursor) -> "Found SQL Injection risk in line 42."`

#### D. Error Panel 🚨
If the system crashes or "Self-Heals", it shows up here.
*   **Stack Traces**: Full python tracebacks.
*   **Fix Attempts**: "Fixer Agent attempted patch 1/3... Failed."

---

## 🎮 Controls

### Pausing & Resuming
Use the **Pause** button to halt the workflow safely. The system will finish the current atomic step and then stop.
Use **Resume** to pick up exactly where you left off.

### Manual Intervention
If the agents get stuck in a "Logic Loop" (arguing with each other), a **"Resolve Conflict"** button will appear. Clicking it allows YOU to break the tie.

---

## 🔧 Troubleshooting

*   **"Dashboard Offline"**: Check if port `3000` or `8080` is blocked.
*   **"No Data"**: Ensure you have actually initialized a project (`./scripts/init.sh init my-project`).
