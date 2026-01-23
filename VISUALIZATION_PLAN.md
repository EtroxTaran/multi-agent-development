# Visualization & Dashboard Implementation Plan

## Goal
Transform the current dashboard into a comprehensive "Command Center" with real-time "Live Graph" visualization of the Multi-Agent System (LangGraph), Human-in-the-Loop (HITL) chat, and advanced UX features using the TanStack ecosystem.

## Tech Stack
- **Frontend:** React, Vite, TypeScript, Tailwind CSS, Radix UI
- **Visualization:** React Flow (@xyflow/react)
- **State/Routing:** TanStack Query, TanStack Router
- **Backend:** FastAPI (Orchestrator API)
- **Communication:** WebSockets (Real-time events), REST API

---

## 📅 Roadmap & Progress

### Phase 1: Backend Event Streaming ✅
Enable real-time visibility into the LangGraph execution.
- [x] **Infrastructure**: Verified `orchestrator-api` WebSocket support.
- [x] **Callback System**: Implemented `WebSocketProgressCallback` in `dashboard/backend/app/callbacks.py`.
- [x] **Integration**: Hooked `WorkflowRunner` in `orchestrator/orchestrator.py` and `routers/workflow.py`.
- [x] **Graph API**: Added `/graph` endpoint to expose topology.

### Phase 2: Frontend Foundation & Project Management ✅
Upgrade the existing dashboard to a "Command Center".
- [x] **Dependencies**: Added `@xyflow/react` and `dagre`.
- [x] **Start Workflow**: Created `StartWorkflowDialog` with flags configuration.
- [x] **Dashboard Integration**: Added Start/Resume buttons to `ProjectDashboard` header.

### Phase 3: The "Live Graph" Visualization ✅
The core visual feature.
- [x] **Graph Component**: Created `WorkflowGraph.tsx`.
- [x] **Data Transformer**: Implemented `dagre` layout for LangGraph definition.
- [x] **Live Updates**: Connected `useWebSocket` to animate nodes on `node_start`/`node_end`.
- [x] **Integration**: Added "Graph" tab to `ProjectDashboard`.

### Phase 4: Human-in-the-Loop (HITL) Interface ✅
Manage interruptions and manual inputs.
- [x] **Interrupt Logic**: Updated `ChatPanel.tsx` to detect `paused` state.
- [x] **Resume Action**: Wired chat input to `useResumeWorkflow` when paused.
- [x] **UI Feedback**: Added visual indicators for "Input Required".

### Phase 5: Advanced UX ("The Extra Mile") 🚧
- [ ] **"Time-Travel" Debugger**: Rollback endpoint exists, UI slider pending.
- [ ] **"Agent Whisperer" Mode**: Metrics streaming enabled, `AgentFeed` can be enhanced.
- [ ] **Predictive Paths**: Graph shows all conditional paths.

---

## Next Steps
- Implement Time-Travel Slider using `useRollbackWorkflow`.
- Enhance `AgentFeed` to show raw token streams if desired.
- Add "Stop" button functionality.