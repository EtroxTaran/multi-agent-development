# Complete Multi-CLI Unified Orchestration System
## Claude Code + Cursor CLI + Gemini CLI in Shared Project Folder

**Research Completed**: January 2026  
**Approach**: Shared Context + Unified Rules + Single Master Conductor  
**Validation**: AGENTS.md Standard, MCP Protocol, Agent Rules Specification  
**Status**: Production-Ready for Implementation  

---

## EXECUTIVE SUMMARY

This architecture enables **three AI agents to work on the same project folder simultaneously** while sharing complete context through:

1. **Unified Rules File** (`AGENTS.md`) - Single source of truth for all agents
2. **Shared Project Context** - All CLIs run in same directory, see same files
3. **Master Conductor** - Bash orchestrator controlling workflow and context flow
4. **Phase-Based Workflow** - Product vision → Planning → Testing → Implementation → Verification
5. **Structured Subfolders** - Each phase gets its own thread with agent contributions

**Key Innovation**: Instead of external orchestration, all three CLIs are **native bash subprocesses of the project**, reading the same `.agent/` configuration folder and `AGENTS.md` ruleset.

---

## VALIDATION FINDINGS

### 1. AGENTS.md Standard (Agent Rules)
✅ **CONFIRMED**: Cross-CLI standard supported by:
- Claude Code: Via `CLAUDE.md` symlink to `AGENTS.md`
- Cursor CLI: Via `.cursor/rules` that references `AGENTS.md`
- Gemini CLI: Via `.gemini/settings.json` with `contextFileName: "AGENTS.md"`

All three can read the same `AGENTS.md` file simultaneously.

### 2. Shared Workspace Pattern
✅ **CONFIRMED**: Multi-agent systems in shared folders working at scale:
- Anthropic: Multi-agent research system with context handoffs
- N8N/CrewAI: Shared environment with MCP protocol
- Industry standard: Use symlinks + single folder + unified config

### 3. Process-Level Context Sharing
✅ **CONFIRMED**: All three CLIs can run from same folder:
```bash
# All three inherit project context automatically
cd /path/to/project
claude code &         # Process 1 - sees entire project
cursor-agent &        # Process 2 - sees entire project  
gemini -p "..." &     # Process 3 - sees entire project
```

Each process has complete file system visibility + reads shared rules from `AGENTS.md`.

### 4. Parallel Execution with Coordination
✅ **CONFIRMED**: Best practices for multi-agent coordination:
- Context Engineering: Use written context (files) as shared memory
- Isolated Scope: Each agent gets scoped window to avoid conflict
- Structured Handoff: JSON state files for inter-agent communication
- Common Ground: Shared rules + unified prompt templates

---

## ARCHITECTURE OVERVIEW

### File Structure (Single Shared Folder)

```
my-project/
├── .agent/                          # UNIFIED AGENT CONFIGURATION
│   ├── AGENTS.md                    # 🌟 SINGLE SOURCE OF TRUTH
│   ├── workflow.json                # Current workflow state
│   ├── context-manifest.json        # What context each agent has access to
│   ├── phase-locks.json             # Prevent parallel modifications
│   └── shared-memory/               # Inter-agent communication
│       ├── product-vision.md        # From discovery phase
│       ├── planning-approved.json   # After all agents agree
│       ├── test-specs.json          # Agreed test plan
│       └── implementation-log.md    # What was built
│
├── CLAUDE.md -> .agent/AGENTS.md    # Symlink: Claude Code reads this
├── .cursor/
│   ├── rules -> ../.agent/AGENTS.md # Symlink: Cursor reads this
│   └── config.toml                  # Cursor-specific settings
│
├── .gemini/
│   ├── settings.json                # Gemini reads AGENTS.md
│   └── agents/
│       ├── planner-prompt.txt
│       ├── reviewer-prompt.txt
│       └── validator-prompt.txt
│
├── src/                             # Source code (all agents modify)
│   └── (project files)
│
├── tests/                           # Tests (all agents modify)
│   └── (test files)
│
├── docs/                            # Documentation (all agents modify)
│   └── (doc files)
│
├── .workflow/                       # WORKFLOW ARTIFACT FOLDERS
│   ├── phase-1-discovery/
│   │   ├── claude-discovery.md
│   │   ├── cursor-feedback.json
│   │   ├── gemini-validation.json
│   │   └── approved-vision.md
│   │
│   ├── phase-2-planning/
│   │   ├── claude-plan.md
│   │   ├── cursor-review.json
│   │   ├── gemini-risks.json
│   │   └── refined-plan.json
│   │
│   ├── phase-3-testing/
│   │   ├── test-spec-created.json
│   │   ├── cursor-test-review.json
│   │   ├── gemini-coverage-analysis.json
│   │   └── approved-tests.md
│   │
│   ├── phase-4-implementation/
│   │   ├── claude-implementation.md
│   │   ├── cursor-code-review.json
│   │   ├── gemini-arch-review.json
│   │   └── implementation-approved.md
│   │
│   ├── phase-5-verification/
│   │   ├── test-results.json
│   │   ├── cursor-final-review.json
│   │   ├── gemini-final-approval.json
│   │   └── production-ready.md
│   │
│   └── logs/
│       ├── claude-session.log
│       ├── cursor-session.log
│       ├── gemini-session.log
│       └── orchestration.log
│
├── .git/
│   └── (all phases tracked in git)
│
└── init-multi-agent.sh              # 🌟 INITIALIZATION SCRIPT
```

### Workflow Phases (with Agent Roles)

```
┌─────────────────────────────────────────────────────────────┐
│ PHASE 1: DISCOVERY                                          │
├─────────────────────────────────────────────────────────────┤
│ Input: Product vision, requirements                         │
│                                                              │
│ Claude Code:     Analyze vision → Create discovery document│
│ Cursor CLI:      Review discovery → Flag missing context   │
│ Gemini CLI:      Validate assumptions → Risk assessment    │
│                                                              │
│ Output: Approved vision (.workflow/phase-1-discovery/)     │
│ All agents MUST agree (JSON signatures)                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 2: PLANNING                                           │
├─────────────────────────────────────────────────────────────┤
│ Input: Approved vision from Phase 1                         │
│                                                              │
│ Claude Code:     Create implementation plan with tasks     │
│ Cursor CLI:      Review plan → Suggest optimizations      │
│ Gemini CLI:      Validate architecture → Flag risks        │
│                                                              │
│ Output: Refined plan (.workflow/phase-2-planning/)         │
│ All agents MUST agree (vote: 3/3)                          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 3: TESTING STRATEGY                                   │
├─────────────────────────────────────────────────────────────┤
│ Input: Refined plan from Phase 2                            │
│                                                              │
│ Claude Code:     Write test specifications & fixtures      │
│ Cursor CLI:      Review test coverage → Flag gaps          │
│ Gemini CLI:      Validate test architecture → Performance  │
│                                                              │
│ Output: Approved tests (.workflow/phase-3-testing/)        │
│ All agents MUST agree                                       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 4: IMPLEMENTATION (TDD)                               │
├─────────────────────────────────────────────────────────────┤
│ Input: Approved tests from Phase 3                          │
│                                                              │
│ Claude Code:     Write production code to pass tests       │
│ Cursor CLI:      Code quality review → Security check      │
│ Gemini CLI:      Architecture review → Performance verify  │
│                                                              │
│ Output: Implemented code (.workflow/phase-4-implementation/)
│ All agents MUST approve                                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PHASE 5: VERIFICATION                                       │
├─────────────────────────────────────────────────────────────┤
│ Input: Implemented code from Phase 4                        │
│                                                              │
│ Tests run:       Verify all tests pass (green)             │
│ Cursor CLI:      Final code review → Production readiness  │
│ Gemini CLI:      Final architecture review → Go/No-Go      │
│                                                              │
│ Output: Production-ready code                               │
│ Gate: All tests green + 3/3 agent approval                 │
└─────────────────────────────────────────────────────────────┘
```

---

## AGENTS.MD - UNIFIED RULES FILE

The **single source of truth** for all agents. All three CLIs read this file.

```markdown
# AGENTS.MD - Unified Agent Rules

**Project**: [Project Name]  
**Vision**: [Product Vision - read from .agent/shared-memory/product-vision.md]  
**Status**: [discovery|planning|testing|implementation|verification]  
**Agents**: Claude Code, Cursor CLI, Gemini CLI  

## CORE PRINCIPLES (All Agents MUST Follow)

### 1. Shared Context Rule
- All agents work in the SAME project folder
- All agents read AGENTS.md as authoritative rules
- All agents save work to .workflow/phase-X-*/ folders
- All agents respect phase-locks.json (no parallel modifications to same file)

### 2. Workflow Integrity
- Each phase must be APPROVED by ALL three agents before proceeding
- Approval = JSON signature in .workflow/phase-X-*/approval.json
- If any agent disagrees, return to previous phase for refinement
- Each phase is IMMUTABLE once approved

### 3. Testing-First Development
- Phase 3 MUST produce passing tests BEFORE Phase 4
- Phase 4 (implementation) is write-code-to-pass-tests ONLY
- No modifying tests to pass code (unless all agents agree AND document why)
- Phase 5 verifies tests still pass after implementation

### 4. Code Quality Standards
- All code must pass:
  - Cursor's code quality review (security + performance + best practices)
  - Gemini's architecture review (scalability + maintainability)
  - 80%+ test coverage minimum
- Type safety required (TypeScript/Python type hints)
- Documentation required inline + in docs/

### 5. Agent Roles

**Claude Code** (Leader/Implementer):
- Leads discovery phase (analyze requirements, create vision)
- Leads planning phase (create task breakdown)
- Leads testing phase (write test specs)
- Leads implementation phase (write code to pass tests)
- Responsible for overall vision coherence

**Cursor CLI** (Code Quality & Security Reviewer):
- Reviews all phases for logical consistency
- Flags security concerns, performance issues
- Checks for best practices adherence
- Validates that code follows architecture
- Final code quality gate

**Gemini CLI** (Architecture & Risk Validator):
- Reviews architecture against scalability requirements
- Identifies technical risks and mitigation strategies
- Validates design patterns and compliance
- Performs performance analysis
- Final architecture gate

### 6. Communication Protocol

**Phase Transitions**:
1. Lead agent (Claude) produces phase deliverable
2. Cursor CLI reviews → approval or blockers JSON
3. Gemini CLI reviews → approval or blockers JSON
4. If blockers exist: Claude refines → return to step 2
5. Once 3/3 approved: move to next phase

**File Locations for Phase X**:
- Claude output: `.workflow/phase-X-*/claude-*.md`
- Cursor review: `.workflow/phase-X-*/cursor-review.json`
- Gemini review: `.workflow/phase-X-*/gemini-review.json`
- Approval votes: `.workflow/phase-X-*/approval.json`
- Next input: `.workflow/phase-X-*/approved-*.md`

### 7. Git & Version Control

- Each phase gets its own commit(s)
- Commit message: `[PHASE-X] <phase-name>: <summary>`
- Only approved phases are committed
- `.workflow/` folder is committed (track agent decisions)
- All agents must verify no conflicts before merge

### 8. Escalation & Conflict Resolution

- If 2 agents disagree with 1: majority votes (refinement required)
- If agents deadlock (2 vs 1): Claude (lead) makes final decision with written justification
- All conflicts documented in `.workflow/phase-X-*/conflicts.md`

### 9. Context Constraints

- Each agent operates within own context window limits
- Large files split with markers: `<!-- CONTEXT-SPLIT: file.ts (1/3) -->`
- Shared memory holds only essential state: `product-vision.md`, `planning-approved.json`, etc.
- Agents MUST NOT duplicate information between phases

### 10. Token Optimization

- Read from `.agent/shared-memory/` for established context
- Write deltas only to phase folders (no full file rewrites)
- Use `.diff` format for code reviews
- Compress context between phases (summarize completed work)

## PHASE SPECIFICATIONS

### PHASE 1: DISCOVERY
**Goal**: Understand requirements and create shared vision  
**Input**: Product requirements (from user or spec)  
**Deliverables**:
- `.workflow/phase-1-discovery/claude-discovery.md` (vision document)
- `.workflow/phase-1-discovery/cursor-feedback.json` (gaps/concerns)
- `.workflow/phase-1-discovery/gemini-validation.json` (risks/mitigations)
- `.workflow/phase-1-discovery/approved-vision.md` (all agents agreed)

**Claude's Discovery Process**:
```
1. Read product requirements
2. Create discovery document:
   - Problem statement
   - Proposed solution
   - Assumptions
   - Success criteria
3. Save to: claude-discovery.md
4. Wait for Cursor + Gemini reviews
```

**Cursor's Review**:
```
1. Read claude-discovery.md
2. Check for:
   - Missing edge cases
   - Logical inconsistencies
   - Security implications
   - Performance considerations
3. Output JSON with:
   {
     "status": "approved|needs_revision|blocked",
     "findings": [
       { "type": "gap|concern|risk", "description": "...", "impact": "low|medium|high" }
     ]
   }
4. Save to: cursor-feedback.json
```

**Gemini's Validation**:
```
1. Read claude-discovery.md + cursor-feedback.json
2. Validate:
   - Architecture assumptions
   - Compliance with standards
   - Scalability implications
   - Risk mitigation adequacy
3. Output JSON with:
   {
     "status": "approved|needs_revision|blocked",
     "architecture_score": 85,
     "risks": [
       { "id": "R1", "description": "...", "mitigation": "..." }
     ]
   }
4. Save to: gemini-validation.json
```

**Approval Gate**:
```
If cursor-feedback.status == "approved" AND gemini-validation.status == "approved":
  → Claude creates approved-vision.md
  → PROCEED TO PHASE 2
Else:
  → Claude reads both reviews
  → Claude refines claude-discovery.md
  → Return to Cursor review
```

### PHASE 2: PLANNING
**Goal**: Create detailed implementation plan with agreed approach  
**Input**: Approved vision from Phase 1  
**Deliverables**:
- `.workflow/phase-2-planning/claude-plan.md` (task breakdown + architecture)
- `.workflow/phase-2-planning/cursor-review.json` (feasibility check)
- `.workflow/phase-2-planning/gemini-risks.json` (technical risks + mitigations)
- `.workflow/phase-2-planning/refined-plan.json` (JSON for testing/implementation)

**Claude's Planning Process**:
```
1. Read approved-vision.md
2. Create claude-plan.md:
   - Architecture overview (diagrams in ASCII)
   - Task breakdown (T001, T002, ...) with dependencies
   - Tech stack selection with rationale
   - Testing strategy (unit, integration, e2e)
   - Deployment plan
3. Save to: claude-plan.md
4. Convert to JSON: refined-plan.json
```

### PHASE 3: TESTING STRATEGY
**Goal**: Write and approve test specifications before implementation  
**Input**: Refined plan from Phase 2  
**Deliverables**:
- `.workflow/phase-3-testing/test-spec-created.json`
- `.workflow/phase-3-testing/cursor-test-review.json`
- `.workflow/phase-3-testing/gemini-coverage-analysis.json`
- `.workflow/phase-3-testing/approved-tests.md`

### PHASE 4: IMPLEMENTATION
**Goal**: Write code to pass approved tests  
**Input**: Approved tests from Phase 3  
**Deliverables**:
- `.workflow/phase-4-implementation/claude-implementation.md` (what was built)
- `.workflow/phase-4-implementation/cursor-code-review.json` (quality gate)
- `.workflow/phase-4-implementation/gemini-arch-review.json` (architecture gate)
- `.workflow/phase-4-implementation/implementation-approved.md` (ready for verification)

### PHASE 5: VERIFICATION
**Goal**: Run tests and get final agent approval  
**Input**: Implemented code + approved tests  
**Deliverables**:
- `.workflow/phase-5-verification/test-results.json` (test suite output)
- `.workflow/phase-5-verification/cursor-final-review.json` (final quality check)
- `.workflow/phase-5-verification/gemini-final-approval.json` (final architecture check)
- `.workflow/phase-5-verification/production-ready.md` (GO/NO-GO decision)

**Verification Gate**:
```
test_results.status == "ALL_PASS" 
  AND cursor-final-review.status == "approved" 
  AND gemini-final-approval.status == "approved"
    → PRODUCTION READY ✅
    → All tests green
    → All agents approve
```

If tests fail:
```
Claude: Analyze test failures
All agents: Review what needs to change
If code needs fixing: Return to Phase 4
If tests need changing: 
  → ALL AGENTS MUST AGREE why
  → Document decision in conflicts.md
  → Return to Phase 3 for re-review
```

## SPECIFIC AGENT INSTRUCTIONS

### CLAUDE CODE Specific Instructions

When running Claude Code in this project:

1. **Initialization**:
   ```
   cd /path/to/project
   claude code --project-dir .
   ```

2. **Read these files first**:
   - `AGENTS.md` (this file)
   - `.agent/workflow.json` (current state)
   - `.agent/shared-memory/product-vision.md` (if exists)

3. **Standard prompt flow**:
   ```
   Claude, you are the lead orchestrator agent in a 3-agent system.
   Read AGENTS.md for your role and responsibilities.
   
   Current phase: [from .agent/workflow.json]
   Phase instructions: [from AGENTS.md PHASE SPECIFICATIONS]
   
   Your task: [specific phase task]
   
   Deliverables:
   - Save output to: .workflow/phase-X-*/<your-output>.md
   - Wait for Cursor and Gemini reviews
   - If blockers: refine based on feedback
   - Once approved: update .agent/workflow.json to next phase
   ```

4. **Phase handoffs**:
   - After producing phase deliverable, call Cursor and Gemini via bash
   - Example:
     ```bash
     # Spawn Cursor review
     cursor-agent -p "$(cat .cursor/prompts/reviewer.txt)" < .workflow/phase-1-discovery/claude-discovery.md > .workflow/phase-1-discovery/cursor-review.json
     
     # Spawn Gemini review
     gemini -p "$(cat .gemini/agents/validator-prompt.txt)" .workflow/phase-1-discovery/claude-discovery.md > .workflow/phase-1-discovery/gemini-review.json
     ```
   - Wait for both to complete
   - Parse JSON responses
   - If approved: proceed
   - If blocked: refine + iterate

### CURSOR CLI Specific Instructions

When Cursor is invoked for review:

1. **Read context**:
   - `AGENTS.md` (your role as Code Quality Reviewer)
   - Phase deliverable to review (passed as input)

2. **Review process**:
   - Check logical consistency
   - Flag security concerns
   - Identify performance issues
   - Verify best practices

3. **Output format** (MUST be valid JSON):
   ```json
   {
     "agent": "cursor",
     "phase": "1",
     "timestamp": "2026-01-19T15:30:00Z",
     "status": "approved|needs_revision|blocked",
     "findings": [
       {
         "severity": "low|medium|high",
         "category": "security|performance|consistency|best_practice",
         "description": "...",
         "suggestion": "..."
       }
     ],
     "summary": "...",
     "confidence": 0.95
   }
   ```

4. **Example review invocation**:
   ```bash
   cursor-agent -p "Review this development plan for security, performance, and best practices:
   $(cat .workflow/phase-1-discovery/claude-discovery.md)
   
   Output MUST be valid JSON in this format:
   {
     \"agent\": \"cursor\",
     \"phase\": \"1\",
     \"status\": \"approved|needs_revision|blocked\",
     \"findings\": [...],
     \"summary\": \"...\",
     \"confidence\": 0.XX
   }"
   ```

### GEMINI CLI Specific Instructions

When Gemini is invoked for validation:

1. **Read context**:
   - `AGENTS.md` (your role as Architecture & Risk Validator)
   - Deliverables to validate (passed as input)

2. **Validation process**:
   - Assess architecture against scalability requirements
   - Identify technical risks
   - Validate design patterns
   - Check compliance

3. **Output format** (MUST be valid JSON):
   ```json
   {
     "agent": "gemini",
     "phase": "1",
     "timestamp": "2026-01-19T15:30:00Z",
     "status": "approved|needs_revision|blocked",
     "architecture_score": 85,
     "risks": [
       {
         "id": "R1",
         "severity": "low|medium|high",
         "description": "...",
         "mitigation": "..."
       }
     ],
     "summary": "...",
     "confidence": 0.92
   }
   ```

4. **Example validation invocation**:
   ```bash
   gemini -p "Validate this architecture for scalability, risks, and design patterns:
   $(cat .workflow/phase-1-discovery/claude-discovery.md)
   
   Also read Cursor's review: $(cat .workflow/phase-1-discovery/cursor-feedback.json)
   
   Output MUST be valid JSON:
   {
     \"agent\": \"gemini\",
     \"phase\": \"1\",
     \"status\": \"approved|needs_revision|blocked\",
     \"architecture_score\": N,
     \"risks\": [...],
     \"summary\": \"...\",
     \"confidence\": 0.XX
   }"
   ```

## TROUBLESHOOTING & EDGE CASES

### Case 1: Agents Deadlock (2 vs 1)
- Claude reviews both positions with written rationale
- Claude makes final decision and documents in `.workflow/phase-X-*/conflicts.md`
- All agents acknowledge decision and proceed

### Case 2: Code Changes Required After Phase 4
- If Cursor or Gemini request changes in Phase 5:
  - Claude implements changes
  - Return to Phase 4 for full re-review
  - DO NOT proceed to Phase 5 until all approve Phase 4 again

### Case 3: Tests Need Modification
- If tests are wrong (not code), ALL agents must agree
- Document agreement in `.workflow/phase-X-*/test-modifications.md`
- Include reasoning from all agents
- Proceed with modified tests + modified code

### Case 4: Long Workflows (Token Overflow)
- Summarize completed phases in `.agent/shared-memory/workflow-summary.md`
- Each agent reads summary instead of full history
- Reduce context window bloat

---

## PROJECT-LEVEL CONFIGURATION

### .agent/workflow.json

```json
{
  "project_name": "My Project",
  "start_date": "2026-01-19",
  "current_phase": "1",
  "phases": {
    "1": {
      "name": "discovery",
      "status": "in_progress",
      "lead": "claude",
      "started_at": "2026-01-19T09:00:00Z",
      "approvals": {
        "claude": null,
        "cursor": null,
        "gemini": null
      },
      "deliverable": ".workflow/phase-1-discovery/approved-vision.md"
    },
    "2": { "name": "planning", "status": "pending", ... },
    "3": { "name": "testing", "status": "pending", ... },
    "4": { "name": "implementation", "status": "pending", ... },
    "5": { "name": "verification", "status": "pending", ... }
  },
  "agents": {
    "claude": {
      "role": "Lead/Implementer",
      "status": "active",
      "current_task": "Analyzing requirements for discovery"
    },
    "cursor": {
      "role": "Code Quality & Security",
      "status": "waiting",
      "current_task": null
    },
    "gemini": {
      "role": "Architecture & Risk",
      "status": "waiting",
      "current_task": null
    }
  },
  "git": {
    "repo": "/path/to/project",
    "branch": "main",
    "last_commit": "abcd1234"
  }
}
```

### .agent/context-manifest.json

```json
{
  "shared_memory": [
    {
      "file": "product-vision.md",
      "phase": 1,
      "accessible_to": ["claude", "cursor", "gemini"],
      "read_only": false
    },
    {
      "file": "planning-approved.json",
      "phase": 2,
      "accessible_to": ["claude", "cursor", "gemini"],
      "read_only": false
    }
  ],
  "phase_artifacts": {
    "phase_1": [
      { "file": "claude-discovery.md", "author": "claude", "read_only": false },
      { "file": "cursor-feedback.json", "author": "cursor", "read_only": false },
      { "file": "gemini-validation.json", "author": "gemini", "read_only": false }
    ]
  }
}
```

### .agent/phase-locks.json

```json
{
  "locks": [
    {
      "file": "src/auth.ts",
      "locked_by": "claude",
      "phase": 4,
      "until": "2026-01-19T15:30:00Z",
      "reason": "Implementation in progress"
    }
  ]
}
```

---

## CLI-SPECIFIC SETUP

### CLAUDE CODE SETUP

Create symlink (all platforms):

**Linux/macOS**:
```bash
ln -s .agent/AGENTS.md CLAUDE.md
```

**Windows**:
```bash
mklink CLAUDE.md .agent\AGENTS.md
```

Add to `.claude/settings.json`:
```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "bash .agent/hooks/claude-session-start.sh"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "bash .agent/hooks/claude-session-end.sh"
      }
    ]
  }
}
```

### CURSOR CLI SETUP

Create symlink in `.cursor/rules`:

**Linux/macOS**:
```bash
ln -s ../.agent/AGENTS.md .cursor/rules
```

**Windows**:
```bash
mklink .cursor\rules ..\.agent\AGENTS.md
```

Create `.cursor/config.toml`:
```toml
[context]
context_file = ".cursor/rules"

[agent]
system_prompt = """You are Cursor, a code quality and security reviewer.
Your instructions are in AGENTS.md. Follow the phase specifications and output JSON.
"""
```

### GEMINI CLI SETUP

Create `.gemini/settings.json`:
```json
{
  "contextFileName": ".agent/AGENTS.md",
  "agents": {
    "validator": {
      "role": "Architecture & Risk Validator",
      "system_prompt": "You are Gemini, an architecture and risk validator.\nYour instructions are in .agent/AGENTS.md.\nOutput valid JSON for all reviews."
    }
  }
}
```

---

## INITIALIZATION SCRIPT

The `init-multi-agent.sh` script sets up everything:

```bash
#!/bin/bash
set -e

PROJECT_DIR="${1:-.}"
cd "$PROJECT_DIR"

echo "🚀 Initializing Multi-Agent System..."

# Create directory structure
mkdir -p .agent/shared-memory
mkdir -p .agent/hooks
mkdir -p .cursor
mkdir -p .gemini/agents
mkdir -p .workflow/logs

# Create AGENTS.md (main rules file)
cat > .agent/AGENTS.md <<'EOF'
[Full AGENTS.MD content from above section]
EOF

# Create symlinks
ln -sf .agent/AGENTS.md CLAUDE.md
ln -sf ../.agent/AGENTS.md .cursor/rules
echo '{"contextFileName": ".agent/AGENTS.md"}' > .gemini/settings.json

# Initialize workflow.json
cat > .agent/workflow.json <<'EOF'
{
  "project_name": "$(basename $(pwd))",
  "start_date": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "current_phase": 1,
  "phases": {
    "1": {"name": "discovery", "status": "ready"},
    "2": {"name": "planning", "status": "pending"},
    "3": {"name": "testing", "status": "pending"},
    "4": {"name": "implementation", "status": "pending"},
    "5": {"name": "verification", "status": "pending"}
  }
}
EOF

# Initialize shared-memory
cat > .agent/shared-memory/product-vision.md <<'EOF'
# Product Vision

(To be filled by Claude in Phase 1)
EOF

# Create initial phase folder
mkdir -p .workflow/phase-1-discovery

# Create Claude session hook
cat > .agent/hooks/claude-session-start.sh <<'EOF'
#!/bin/bash
echo "[$(date)] Claude session started in phase: $(jq -r '.current_phase' .agent/workflow.json)"
EOF

chmod +x .agent/hooks/claude-session-start.sh

# Add to git
echo ".agent/" >> .gitignore
echo ".workflow/logs/" >> .gitignore

git add .agent CLAUDE.md .cursor .gemini .gitignore
git commit -m "Initialize multi-agent system with AGENTS.md"

echo "✅ Multi-agent system initialized!"
echo ""
echo "Next steps:"
echo "1. Update .agent/AGENTS.md with your project-specific rules"
echo "2. Start Claude Code: cd $(pwd) && claude code"
echo "3. Claude will orchestrate the workflow with Cursor and Gemini"
echo ""
echo "View workflow status: cat .agent/workflow.json"
```

---

## BEST PRACTICES FOR THIS ARCHITECTURE

### 1. Context Management
- ✅ Use `.agent/shared-memory/` for established context (reused across phases)
- ✅ Use `.workflow/phase-X-*/` for phase-specific artifacts
- ✅ Read AGENTS.md at start of each phase
- ❌ Don't duplicate information between agents
- ❌ Don't pass entire codebase between phases

### 2. Token Optimization
- ✅ Use `.diff` format for code reviews
- ✅ Reference previous phase outputs instead of repeating
- ✅ Compress summaries after each phase
- ✅ Store state in JSON (compact) not markdown

### 3. Parallel Execution
- ✅ Run Cursor and Gemini reviews in parallel (use `&` in bash)
- ✅ Use phase-locks to prevent simultaneous edits
- ✅ Spawn agents as background processes from Claude
- ✅ Wait for completion before proceeding

### 4. Error Recovery
- ✅ Commit state after each phase (full git history)
- ✅ Store logs in `.workflow/logs/` for debugging
- ✅ Document all agent decisions in JSON
- ✅ Implement retry logic for agent failures

### 5. Production Readiness
- ✅ All tests must pass (Phase 5 gate)
- ✅ All agents must approve (3/3 votes)
- ✅ No code without tests (Phase 3 → Phase 4)
- ✅ No skipping phases

---

## NEXT: IMPLEMENTATION CHECKLIST

When ready to code this system, a developer should:

- [ ] Copy `init-multi-agent.sh` to project root
- [ ] Run `bash init-multi-agent.sh` to initialize everything
- [ ] Customize `AGENTS.md` with project-specific rules
- [ ] Create phase-specific prompts for each CLI
- [ ] Test each CLI individually in the project
- [ ] Run a test workflow with a small feature
- [ ] Verify all phases complete and agents approve
- [ ] Deploy to production pipeline

---

**This document is the blueprint. The coding agent will implement the initialization script and all supporting structures.**
