# Complete Agent Registry

Conductor orchestrates a total of **14 Specialized Agents** and several supporting infrastructure agents.

This registry documents every active agent in the system.

---

## 🎖️ The Specialist Squad (A01-A12)

These 12 agents handle the core SDLC.

| ID | Name | Role | Primary CLI |
|----|------|------|-------------|
| **A01** | **Planner** | Task Breakdown & Dependencies | Claude |
| **A02** | **Architect** | Design & Scalability Review | Gemini |
| **A03** | **Test Writer** | TDD Implementation | Claude |
| **A04** | **Implementer** | Code Generation | Claude |
| **A05** | **Bug Fixer** | Debugging & Stack Trace Analysis | Cursor |
| **A06** | **Refactorer** | Code Improvements | Gemini |
| **A07** | **Security Reviewer** | OWASP Vulnerability Check | Cursor |
| **A08** | **Code Reviewer** | Style & Quality Check | Gemini |
| **A09** | **Docs Writer** | Documentation & Comments | Claude |
| **A10** | **Integration Tester** | End-to-End Testing | Claude |
| **A11** | **DevOps** | CI/CD & Infrastructure | Cursor |
| **A12** | **UI Designer** | Frontend & UX | Claude |

---

## 🚑 Emergency & Support Agents

These agents operate outside the standard flow to handle special cases.

### SPEC-01: The Fixer Agent
*   **Role**: Autonomous Self-Healing.
*   **Trigger**: Activated when a test fails or a crash occurs.
*   **Capabilities**:
    *   **Triage**: Is it a syntax error (easy) or logic error (hard)?
    *   **Circuit Breaker**: Stops after 3 attempts to prevent infinite loops.
    *   **Patching**: Applies surgical fixes to broken code.

### SPEC-02: The Research Agent
*   **Role**: Pre-Planning analysis.
*   **Trigger**: Before Phase 1 (Planning) begins.
*   **Capabilities**:
    *   **Tech Stack Analyzer**: Identifies existing libraries to prevent "Dependency Hell".
    *   **Pattern Analyzer**: Reads existing code to ensure new code matches the style.
    *   **Parallelism**: Runs 2 sub-agents simultaneously to scan the repo fast.

---

## 🤖 CLI Wrappers (The Infrastructure)

These are the python classes that interface with the external AI binary.

### CLI-01: ClaudeAgent
*   **Wrapper For**: `claude-code`
*   **Features**: Plan Mode detection, Budget management, Session continuity.

### CLI-02: CursorAgent
*   **Wrapper For**: `cursor` (IDE CLI)
*   **Features**: Security-optimized system prompts, Local file context access.

### CLI-03: GeminiAgent
*   **Wrapper For**: `gemini-cli`
*   **Features**: 1M+ Token Context Window (repo-wide understanding), Zero-latency architecture checks.

---

## 🧠 LangGraph Nodes

Some "Agents" are actually deterministic graph nodes that facilitate decisions.

*   **DiscussPhase**: Interviews the user to capture preferences.
*   **FixerTriage**: Routes errors to the correct fixer strategy.
*   **VerificationGate**: Aggregates scores from A07/A08 and decides Pass/Fail.
