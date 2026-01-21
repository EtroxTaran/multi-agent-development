# Multi-Agent Orchestration with Shared Project Context
## Comprehensive Architecture, Configuration & Initialization Guide

**Version**: 2.0 (Shared Context Pattern)
**Date**: January 2026
**Status**: Production-Ready Implementation Guide

---

## TABLE OF CONTENTS

1. [Executive Summary](#executive-summary)
2. [Core Architecture: Shared Project Context Pattern](#core-architecture)
3. [How Each CLI Operates in Shared Context](#how-each-cli-works)
4. [Workflow Phases & Agent Responsibilities](#workflow-phases)
5. [Complete Configuration Guide](#configuration-guide)
6. [Initialization Script (init-multi-agent.sh)](#initialization-script)
7. [Product Vision Workflow Specification](#product-vision-workflow)
8. [Implementation Patterns & Best Practices](#implementation-patterns)
9. [Real-World Example](#real-world-example)
10. [Troubleshooting & Advanced Patterns](#troubleshooting)

---

## EXECUTIVE SUMMARY

**Key Insight**: Instead of separate CLI instances working independently, all three CLI tools (Claude Code, Cursor, Gemini CLI) **run in the same project folder** as subprocesses, inheriting complete project context through shared files and configuration.

**Advantages**:
- ✅ All agents see identical project structure, rules, and settings
- ✅ No context loss between agent handoffs (file-system-as-state)
- ✅ True parallel execution with coordination through `.workflow/` directory
- ✅ Single source of truth for product vision, tasks, and status
- ✅ Shared rules prevent agent misalignment
- ✅ Natural workflow progression: vision → plan → test → implement → verify

**Architecture**:
```
Project Folder (Shared Context)
├── Product Vision (PRODUCT.md)
├── Shared Rules (.rules/, .agents/, AGENTS.md)
├── CLI Configurations (.claude/, .cursor/, .gemini/)
├── .workflow/
│   ├── phases/
│   │   ├── 01-planning/
│   │   ├── 02-testing/
│   │   ├── 03-implementation/
│   │   └── 04-verification/
│   ├── state.json (current phase/status)
│   ├── vision-snapshot.md (current goals)
│   └── coordination.log
├── Source code
└── Tests
```

---

## CORE ARCHITECTURE: SHARED PROJECT CONTEXT PATTERN

### Why This Works

**File-System-as-State Philosophy**:
- Each CLI subprocess inherits the complete project directory as its working context
- No API calls needed between agents; they communicate through files
- State is persistent and visible in `.workflow/` directory
- Each agent reads its task, reads shared context, executes, writes results

### Three CLI Integration Points

| CLI | How It's Called | Context Access | State Persistence |
|-----|-----------------|-----------------|------------------|
| **Claude Code** | `claude -p "prompt" --append-system-prompt-file=.claude/system.md` | Full project + `.claude/` config | `--continue` flag maintains context |
| **Cursor CLI** | `cursor-agent -p "prompt" --rules .cursor/rules` | Full project + `.cursor/` config | File-based handoff |
| **Gemini CLI** | `gemini -p "prompt" -e agent-name` | Full project + `.gemini/` config | Task queue in `.gemini/tasks/` |

### Orchestration Flow

```
Master Orchestrator (Python/Bash)
    ↓
    ├─ Reads PRODUCT.md (vision) + state.json (current phase)
    ├─ Generates phase-specific task for active agent
    ├─ Invokes Claude Code | Cursor CLI | Gemini CLI as subprocess
    ├─ All three CLIs share same working directory
    ├─ Subprocess completes, writes results to .workflow/
    ├─ Orchestrator verifies completion
    └─ Loops to next phase

Benefits:
• All agents see exact same project state
• No context corruption between handoffs
• Git can track .workflow/ artifacts
• Failed agent runs are debuggable (logs in .workflow/)
```

---

## HOW EACH CLI OPERATES IN SHARED CONTEXT

### Claude Code in Shared Context

**Execution**:
```bash
cd /path/to/project
claude -p "You are the planner agent. Your task: analyze PRODUCT.md and create plan.json" \
  --append-system-prompt-file=.claude/system.md \
  --allowedTools "Bash(git*),Bash(npm*),Bash(test*)" \
  --continue  # Maintain context if resuming
```

**What Claude Code Can Do**:
- ✅ Read any file in project (no restrictions)
- ✅ Execute bash commands (sandboxed via `--allowedTools`)
- ✅ Write files with `Edit` tool (logged in hooks)
- ✅ Access .claude/ configuration automatically
- ✅ Use `--continue` to maintain state across phases
- ✅ Create sub-agents for parallel tasks

**Files Claude Reads**:
- `PRODUCT.md` (vision/goals)
- `.workflow/state.json` (current phase)
- `.workflow/phases/*/` (previous phase outputs)
- `.claude/system.md` (system prompt)
- `.claude/rules/` (project rules, recursively)
- Any source code (inherited context)

**Files Claude Writes**:
- `.workflow/phases/01-planning/plan.json`
- `.workflow/phases/01-planning/PLAN.md`
- Test files, implementation, etc.

**Hooks in Claude**:
- `PreToolUse`: Validate commands before execution
- `PostToolUse`: Log all file changes, validate quality
- `Stop`: Ask "Are all planning tasks complete?"

---

### Cursor CLI in Shared Context

**Execution**:
```bash
cd /path/to/project
cursor-agent -p "You are the reviewer agent. Your task: read plan.json and provide feedback" \
  --rules .cursor/rules
```

**What Cursor Can Do**:
- ✅ Read project files in working directory
- ✅ Provide code review with diffs
- ✅ Run tests (via bash)
- ✅ Write structured feedback
- ✅ Use `.cursor/rules` for consistency
- ✅ Access AGENTS.md for coordination

**Files Cursor Reads**:
- `PRODUCT.md` (for context alignment)
- `.workflow/phases/01-planning/plan.json` (artifact to review)
- `.cursor/rules` (project-specific guidelines)
- `AGENTS.md` (shared agent definitions)
- Source code files being reviewed

**Files Cursor Writes**:
- `.workflow/phases/02-review/cursor-feedback.json`
- `.workflow/phases/02-review/cursor-feedback.md`
- Review diffs in `.workflow/phases/02-review/diffs/`

**Cursor Integration**:
- Print mode (`-p`) for automation
- Rules drive behavior (consistency across runs)
- Scope to specific folders if needed (e.g., `src/`)

---

### Gemini CLI in Shared Context

**Execution**:
```bash
cd /path/to/project
gemini -p "You are the validator agent. Your task is in .workflow/current-task.json" \
  -e validator-agent  # Load validator-agent extension
```

**What Gemini Can Do**:
- ✅ Read project structure and context
- ✅ Execute validation tasks (linting, testing)
- ✅ Run in parallel without conflicts (isolated containers)
- ✅ Use `.gemini/` configuration
- ✅ Access MCP servers for extensions
- ✅ Write task results to `.gemini/tasks/completed/`

**Files Gemini Reads**:
- `PRODUCT.md` (understanding scope)
- `.workflow/phases/*/` (outputs to validate)
- `.gemini/GEMINI.md` (identity/context)
- `AGENTS.md` (shared definitions)

**Files Gemini Writes**:
- `.gemini/tasks/completed/{task-id}.json` (validation result)
- `.workflow/phases/04-verification/gemini-validation.md`
- Test results, validation logs

**Gemini Task Queue**:
```bash
# Task gets queued
echo '{"task": "validate_tests", "target": "spec/"}' > .gemini/tasks/pending/task-001.json

# Gemini CLI processes it
gemini -p "Process pending task at .gemini/tasks/pending/task-001.json"

# Writes result
# .gemini/tasks/completed/task-001.json
```

---

## WORKFLOW PHASES & AGENT RESPONSIBILITIES

### Phase-Based Structure

All work flows through phases stored in `.workflow/phases/`:

```
.workflow/
├── phases/
│   ├── 01-planning/
│   │   ├── PLAN.md
│   │   ├── plan.json (structured)
│   │   ├── tasks-breakdown.json
│   │   └── dependencies.json
│   │
│   ├── 02-test-design/
│   │   ├── tests.md
│   │   ├── test-spec.json
│   │   ├── coverage-goals.json
│   │   └── test-verification.json (Cursor/Gemini feedback)
│   │
│   ├── 03-implementation/
│   │   ├── implementation.md
│   │   ├── code-changes.json
│   │   ├── test-results.json
│   │   └── implementation-log.md
│   │
│   ├── 04-verification/
│   │   ├── code-review.md
│   │   ├── cursor-review.json
│   │   ├── gemini-validation.json
│   │   ├── test-verification-final.md
│   │   └── ready-to-merge.json
│   │
│   └── 05-completion/
│       ├── summary.md
│       ├── changes-summary.json
│       └── completion-checklist.json
│
└── state.json → Points to current phase
```

### Phase Workflow with Agent Coordination

#### Phase 1: PLANNING (Claude Code)

**Input**: 
- `PRODUCT.md` (user's vision and next steps)
- `state.json` (workflow state)

**Process**:
1. Claude reads PRODUCT.md and current goals
2. Breaks down into concrete tasks
3. Identifies dependencies
4. Creates test strategy
5. Writes plan to `.workflow/phases/01-planning/`

**Output**:
```json
// plan.json
{
  "phase": "planning",
  "tasks": [
    {
      "id": "t1",
      "title": "Create auth service",
      "description": "Implement JWT auth with refresh tokens",
      "dependencies": [],
      "estimated_complexity": "high",
      "test_strategy": "Unit tests for token generation/validation"
    }
  ],
  "dependencies": {
    "t2": ["t1"],  // t2 depends on t1
    "t3": ["t1", "t2"]
  },
  "risks": ["Token expiration edge cases"],
  "completion_criteria": "All tests pass, code reviewed"
}
```

**Status**: ✅ Phase complete → Advance to Phase 2

---

#### Phase 2: TEST DESIGN & VALIDATION (Cursor + Gemini in Parallel)

**Cursor's Role: Review Plan**
```bash
cursor-agent -p "Review the plan in .workflow/phases/01-planning/plan.json.
Check for logical errors, missing edge cases, security concerns.
Provide feedback in JSON format."
```

**Gemini's Role: Validate Plan**
```bash
gemini -p "Validate the plan against architecture best practices.
Check scalability, design patterns, compliance.
Provide validation result in JSON."
```

**Coordination**:
- Both run in parallel (added `&` to background jobs)
- Both read from same `.workflow/phases/01-planning/`
- Both write to different files (no conflicts)
- Orchestrator waits for both to complete

**Outputs**:
```
.workflow/phases/02-test-design/
├── cursor-feedback.json → Code quality concerns
├── gemini-validation.json → Architecture validation
└── consolidated-feedback.md → Combined issues for Claude to address
```

**Status**: ✅ Reviews complete → Claude refines plan or moves to Phase 3

---

#### Phase 3: IMPLEMENTATION (Claude Code)

**Input**:
- Refined plan from Phase 1
- Feedback from Phase 2 (consolidated in `consolidated-feedback.md`)

**Process**:
1. Claude reads feedback
2. Writes tests first (TDD)
3. Implements to pass tests
4. Runs tests locally
5. Commits with clear messages
6. Documents any deviations

**Output**:
```
.workflow/phases/03-implementation/
├── implementation.md → Narrative of work done
├── test-results.json → All tests passed ✅
├── code-changes.json → List of modified files
└── implementation-log.md → Detailed log with decisions
```

**Status**: ✅ All tests pass → Advance to Phase 4

---

#### Phase 4: VERIFICATION & REVIEWS (Cursor + Gemini in Parallel)

**Cursor's Role: Code Quality Review**
```bash
cursor-agent -p "Review all implementation in .workflow/phases/03-implementation/.
Check code quality, test coverage, security.
Is this ready for production?"
```

**Gemini's Role: Architecture + Test Validation**
```bash
gemini -p "Validate implementation matches architecture plan.
Verify all tests are comprehensive.
Run final test verification.
Approve or flag issues."
```

**Outputs**:
```
.workflow/phases/04-verification/
├── cursor-review.json → Code quality: ✅ APPROVED
├── gemini-validation.json → Architecture: ✅ APPROVED
├── final-test-results.md → All tests: ✅ PASSING
└── ready-to-merge.json → {"status": "READY", "approved_by": ["cursor", "gemini"]}
```

**Status**: ✅ All verifications pass → Phase 5

---

#### Phase 5: COMPLETION & NEXT STEPS

**Orchestrator**:
1. Verifies all approvals in place
2. Creates completion summary
3. Asks: Read PRODUCT.md → More features to implement?
4. If YES: Loop back to Phase 1 with new task
5. If NO: Mark workflow complete

**Output**:
```
.workflow/phases/05-completion/
├── summary.md → What was accomplished
├── changes-summary.json → All files modified
├── metrics.json → Tokens used, time taken, tests passed
└── next-steps.json → {"recommendation": "implement_mfa", "or": "ship_to_production"}
```

---

## CONFIGURATION GUIDE

### Essential Configuration Files

#### 1. `.claude/system.md` (Claude Code System Prompt)

```markdown
# Claude Code System Prompt - Multi-Agent Orchestrator

You are Claude Code operating in a multi-agent system alongside Cursor and Gemini CLI.

## Your Role
- **Planning Agent**: Break down PRODUCT.md into concrete, testable tasks
- **Implementation Agent**: Write tests first, then implementation
- **Coordinator**: Read feedback from other agents, incorporate and improve

## Context Files You Access
- `PRODUCT.md` - Product vision and next steps (always read this first)
- `.workflow/state.json` - Current phase and workflow status
- `.workflow/phases/*/` - Previous phase outputs and feedback
- `.claude/rules/` - Project-specific rules (read recursively)
- `AGENTS.md` - Shared agent definitions and responsibilities

## Current Phase: {PHASE}
Your task for this phase is in: .workflow/phases/{PHASE_NUM}-{PHASE_NAME}/task.json

## Critical Rules
1. **Always read PRODUCT.md first** - This is your north star
2. **Read feedback from other agents** - Cursor and Gemini may have flagged issues
3. **Test-first approach** - Never implement without tests
4. **Document decisions** - Write to .workflow/phases/{PHASE}/implementation.md
5. **Fail safely** - If unsure, ask via prompt or write to .workflow/blockers.md

## Output Format
All JSON outputs must follow the schema in `.workflow/schemas/`

## Success Criteria
- Code passes all tests
- Feedback from Cursor and Gemini = APPROVED
- Commit messages are clear and reference task IDs
```

#### 2. `.cursor/rules` (Cursor Agent Rules)

```markdown
# Cursor Agent Rules - Code Review & Architecture Verification

## Your Role
You are a specialized code reviewer in a multi-agent system.

### Responsibilities
1. **Code Quality Review**
   - Check readability, maintainability, design patterns
   - Flag security issues and performance concerns
   - Verify test coverage (target: 80%+)

2. **Architecture Validation**
   - Ensure code matches planned architecture
   - Check SOLID principles adherence
   - Verify no technical debt introduced

3. **Communication**
   - Provide structured feedback in JSON format
   - Reference specific line numbers and files
   - Suggest fixes, don't just criticize

### Context Files
- Read: PRODUCT.md (understand scope)
- Read: .workflow/phases/{current}/ (artifact being reviewed)
- Read: AGENTS.md (understand other agents' roles)

### Review Checklist
- [ ] Code follows language style guide
- [ ] No security vulnerabilities
- [ ] Adequate test coverage
- [ ] Performance acceptable
- [ ] Error handling complete
- [ ] Documentation clear

### Feedback Format
Always respond with JSON:
```json
{
  "overall_verdict": "approved|revision_required|blocked",
  "quality_score": 0-100,
  "critical_issues": [...],
  "warnings": [...],
  "suggestions": [...],
  "approved_by_cursor": true/false
}
```

### Important
- Use print mode (-p) for automation
- Reference PRODUCT.md context when making judgment calls
- Coordinate with Gemini (both validate together)
```

#### 3. `.gemini/GEMINI.md` (Gemini CLI Identity & Context)

```markdown
# Gemini CLI Configuration - Validator Agent

## Identity
You are the Validator Agent in a multi-agent orchestration system.
Your role: Verify correctness, architecture adherence, and test completeness.

## Responsibilities
1. **Implementation Validation**
   - Run all tests and report results
   - Check architecture matches plan
   - Verify compliance with PRODUCT.md goals

2. **Test Verification**
   - Ensure tests cover edge cases
   - Check for missing test scenarios
   - Validate test quality and clarity

3. **Architecture Review**
   - Verify design patterns are correct
   - Check scalability considerations
   - Ensure technical debt is minimal

## Context Access
- PRODUCT.md: Product vision and goals
- .workflow/phases/: All phase artifacts
- AGENTS.md: Agent roles and coordination
- .gemini/tasks/: Your task queue

## Task Processing
When processing tasks:
1. Read task definition from .gemini/tasks/pending/
2. Execute validation
3. Write result to .gemini/tasks/completed/
4. Update .workflow/phases/{current}/gemini-validation.json

## Validation Output Format
```json
{
  "validator": "gemini",
  "status": "approved|revision_required|blocked",
  "checks": {
    "tests_passing": true,
    "architecture_valid": true,
    "coverage_sufficient": true
  },
  "findings": [
    {"severity": "error|warning|info", "message": "..."}
  ],
  "approved_by_gemini": true/false
}
```

## Parallel Execution
You may run in parallel with Cursor. Coordinate via:
- .workflow/coordination.log
- .workflow/phases/{current}/ (read, don't overwrite)
```

#### 4. `AGENTS.md` (Shared Agent Definitions)

```markdown
# Shared Agent Definitions & Coordination Protocol

This file is read by all agents (Claude, Cursor, Gemini) to understand each other's roles.

## Agent Roles

### Claude Code - Orchestrator & Implementer
- **Phase 1**: Planning - break down PRODUCT.md into tasks
- **Phase 3**: Implementation - write tests, implement, validate
- **Capabilities**: Full project context, bash execution, file creation
- **Output Format**: JSON plans, implementation logs, test results

### Cursor - Reviewer & Architect
- **Phase 2**: Review - validate plan quality and architecture
- **Phase 4**: Review - code quality and compliance verification
- **Capabilities**: Code review with diffs, architecture analysis, security checks
- **Output Format**: Structured JSON feedback with severity levels

### Gemini - Validator & Test Verifier
- **Phase 2**: Validate - architecture and design verification
- **Phase 4**: Verify - test completeness and results
- **Capabilities**: Test execution, validation, parallel processing
- **Output Format**: Validation results in JSON format

## Coordination Rules

### 1. Context Sharing
- **Single Source of Truth**: PRODUCT.md (product vision)
- **State Management**: .workflow/state.json (current phase)
- **Phase Artifacts**: .workflow/phases/{num}-{name}/ (read/write own phase)

### 2. Handoff Protocol
Each phase handoff follows:
```
Previous Agent → Writes to: .workflow/phases/{num}/output.json
Current Agent → Reads from: .workflow/phases/{num}/output.json
Current Agent → Reads feedback: .workflow/phases/{num}/feedback.json
Current Agent → Writes to: .workflow/phases/{num}/result.json
```

### 3. Parallel Execution Guidelines
When Cursor and Gemini run in parallel:
- Both read same artifact (e.g., plan.json)
- Each writes to own file (cursor-feedback.json, gemini-validation.json)
- Orchestrator merges feedback in consolidated-feedback.md
- No file conflicts (separate namespaces)

### 4. Approval Gates
- **Phase 2**: Both Cursor AND Gemini must approve (type: "revision_required" → loop back to Claude)
- **Phase 4**: Both Cursor AND Gemini must approve OR mark "blocked" (stop workflow)
- **Criteria**: Check .workflow/phases/{num}/{agent}-validation.json for approval field

### 5. Conflict Resolution
If agents disagree:
- **Priority**: Architecture (Gemini) > Code Quality (Cursor) > Implementation (Claude)
- **Resolution**: Claude reads both feedbacks, makes decision, documents in .workflow/phases/decision-log.md
- **Escalation**: If unresolvable, set .workflow/blocker.json and wait for user

## Communication
- Via .workflow/coordination.log
- Via .workflow/blockers.json (for issues)
- Via phase-specific feedback files (structured)

## Success Definition
- All tests passing
- All agents approved (approval_status: "approved")
- No blockers set
- PRODUCT.md goals achieved
```

#### 5. `PRODUCT.md` (Product Vision Template)

```markdown
# Product Vision & Development Roadmap

## Current Goal / Feature
[User-facing feature or goal description]

### Acceptance Criteria
- [ ] Criteria 1
- [ ] Criteria 2
- [ ] Criteria 3

### Technical Constraints
- Framework/language: 
- Performance requirements:
- Security requirements:

### Architecture Notes
[Any architectural decisions or constraints]

## Next Steps
[If previous feature was completed, what's next?]

## Phase Progress
- [ ] Phase 1: Planning (Claude Code) - Estimate: 5 min
- [ ] Phase 2: Test Design & Validation (Cursor + Gemini) - Estimate: 10 min
- [ ] Phase 3: Implementation (Claude Code) - Estimate: 20 min
- [ ] Phase 4: Verification (Cursor + Gemini) - Estimate: 10 min
- [ ] Phase 5: Completion (Orchestrator) - Estimate: 2 min

**Total Estimated Time**: ~50 minutes per feature

## How to Use This File
1. Owner updates "Current Goal / Feature" section
2. Set acceptance criteria
3. Run: `python .workflow/orchestrator.py --start`
4. Orchestrator reads this file and begins Phase 1
5. As phases complete, orchestrator updates this file with checkmarks
```

---

## INITIALIZATION SCRIPT

### `init-multi-agent.sh` - Complete Project Setup

This script initializes a new project with full multi-agent orchestration support.

**Usage**:
```bash
curl -fsSL https://path/to/init-multi-agent.sh | bash -s -- my-project
# OR
chmod +x init-multi-agent.sh
./init-multi-agent.sh my-project
```

**Full Script**:

```bash
#!/bin/bash
#
# init-multi-agent.sh
# Initialize multi-agent orchestration for Claude Code, Cursor, and Gemini CLI
# Works in any project folder
#
# Usage: ./init-multi-agent.sh [project_name]

set -e

PROJECT_NAME="${1:-.}"
PROJECT_DIR="$(cd "$PROJECT_NAME" 2>/dev/null && pwd || mkdir -p "$PROJECT_NAME" && cd "$PROJECT_NAME" && pwd)"

echo "🚀 Multi-Agent Orchestration Setup"
echo "📂 Project: $PROJECT_DIR"
echo ""

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_step() {
    echo -e "${BLUE}→${NC} $1"
}

log_done() {
    echo -e "${GREEN}✓${NC} $1"
}

log_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Step 1: Create directory structure
log_step "Creating directory structure..."

mkdir -p "$PROJECT_DIR"/.workflow/{phases/{01-planning,02-test-design,03-implementation,04-verification,05-completion},schemas,logs}
mkdir -p "$PROJECT_DIR"/.claude/{rules,hooks,memories}
mkdir -p "$PROJECT_DIR"/.cursor
mkdir -p "$PROJECT_DIR"/.gemini/{agents,tasks/{pending,completed}}
mkdir -p "$PROJECT_DIR"/.rules
mkdir -p "$PROJECT_DIR"/src
mkdir -p "$PROJECT_DIR"/spec

log_done "Directories created"

# Step 2: Create shared rule files
log_step "Creating shared rule files..."

cat > "$PROJECT_DIR/.rules/base-rules.md" << 'EOF'
# Base Rules for All Agents

## Code Style
- Use consistent formatting (prettier/black)
- Clear variable names (no abbreviations)
- Comments for complex logic
- Max line length: 100 characters

## Testing
- Test-first approach (TDD)
- Minimum 80% coverage
- Test names describe what they verify
- Edge cases must have tests

## Git Practices
- Commit messages: [TASK-ID] Brief description
- Atomic commits (one logical change)
- Push to feature branch first
- PR review before main

## Security
- No secrets in code (use .env)
- Input validation always
- SQL/Command injection prevention
- CORS/CSRF protection
EOF

cat > "$PROJECT_DIR/.rules/architecture.md" << 'EOF'
# Architecture Guidelines

## Layering
- Controllers/Routes: API endpoints
- Services: Business logic
- Repositories: Data access
- Models: Data structures

## Dependencies
- Inversion of Control (IoC)
- Dependency Injection for services
- No circular dependencies
- Clear module boundaries

## Error Handling
- Consistent error response format
- Log all errors with context
- User-friendly error messages
- Proper HTTP status codes

## Performance
- Cache frequently accessed data
- Optimize database queries
- Lazy load dependencies
- Monitor response times
EOF

log_done "Rule files created"

# Step 3: Create Claude Code configuration
log_step "Creating Claude Code configuration..."

cat > "$PROJECT_DIR/.claude/system.md" << 'EOF'
# Claude Code System Prompt - Multi-Agent Orchestrator

You are Claude Code in a multi-agent system with Cursor and Gemini CLI.

## Context Sources (Read First)
1. PRODUCT.md - Current goal and acceptance criteria
2. .workflow/state.json - Current workflow phase
3. .workflow/phases/*/feedback.json - Feedback from other agents
4. .rules/ - Shared project rules
5. .claude/rules/ - Claude-specific rules

## Phases & Your Responsibilities

### Phase 1: Planning
- Read PRODUCT.md
- Break down into concrete tasks
- Create dependency graph
- Identify test strategy
- Output: .workflow/phases/01-planning/plan.json

### Phase 3: Implementation
- Read refined plan and feedback
- Write tests first (TDD)
- Implement to pass tests
- Run tests locally
- Document decisions
- Output: .workflow/phases/03-implementation/

## Critical Rules
- Always read PRODUCT.md first
- Incorporate feedback from Cursor and Gemini
- Never commit without test verification
- Document all decisions in .workflow/implementation-log.md
- Write JSON outputs according to .workflow/schemas/

## Success Criteria
- Tests passing (100%)
- Approved by both Cursor and Gemini
- Code quality high (no tech debt)
- PRODUCT.md goals achieved
EOF

cat > "$PROJECT_DIR/.claude/settings.json" << 'EOF'
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/pre-bash-check.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/post-edit-log.sh"
          }
        ]
      }
    ]
  },
  "permissions": {
    "defaultBashPermission": "ask"
  }
}
EOF

mkdir -p "$PROJECT_DIR/.claude/hooks"

cat > "$PROJECT_DIR/.claude/hooks/pre-bash-check.sh" << 'EOF'
#!/bin/bash
# Pre-bash validation hook
# Prevents dangerous commands from executing

COMMAND="$1"

# Dangerous patterns
if [[ "$COMMAND" =~ "rm -rf /" ]] || [[ "$COMMAND" =~ "sudo shutdown" ]]; then
    echo "❌ Dangerous command blocked: $COMMAND" >&2
    exit 1
fi

exit 0
EOF

chmod +x "$PROJECT_DIR/.claude/hooks/pre-bash-check.sh"

cat > "$PROJECT_DIR/.claude/hooks/post-edit-log.sh" << 'EOF'
#!/bin/bash
# Post-edit logging hook

LOG_FILE="$CLAUDE_PROJECT_DIR/.workflow/logs/edits.log"
TIMESTAMP=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

echo "[$TIMESTAMP] File edit: $1" >> "$LOG_FILE"
EOF

chmod +x "$PROJECT_DIR/.claude/hooks/post-edit-log.sh"

log_done "Claude Code configured"

# Step 4: Create Cursor configuration
log_step "Creating Cursor configuration..."

cat > "$PROJECT_DIR/.cursor/rules" << 'EOF'
# Cursor Agent Rules - Code Review & Architecture

## Your Role
You are the code reviewer and architecture validator.

## Responsibilities
1. Review code quality (style, maintainability, design patterns)
2. Validate architecture against plan
3. Check security and performance
4. Verify test coverage (target: 80%+)

## Context Files
- PRODUCT.md (scope and goals)
- .rules/ (shared project rules)
- .workflow/phases/ (artifacts being reviewed)
- AGENTS.md (understand other agents)

## Review Checklist
- Code quality and style compliance
- Security vulnerabilities check
- Performance concerns
- Test coverage adequate
- Error handling complete
- Documentation clear

## Feedback Format
Respond with structured JSON:
{
  "overall_verdict": "approved|revision_required|blocked",
  "score": 0-100,
  "critical": [...],
  "warnings": [...],
  "approved": true/false
}

## Important
- Use -p flag for automation
- Reference PRODUCT.md when applicable
- Coordinate with Gemini (both validate together)
EOF

log_done "Cursor configured"

# Step 5: Create Gemini CLI configuration
log_step "Creating Gemini CLI configuration..."

cat > "$PROJECT_DIR/.gemini/GEMINI.md" << 'EOF'
# Gemini CLI - Validator Agent

## Identity
You are the Validator Agent - responsible for test verification and architecture validation.

## Responsibilities
1. Run all tests and report results
2. Validate architecture correctness
3. Check code against PRODUCT.md goals
4. Verify no regressions

## Context
- PRODUCT.md: Goals and requirements
- .rules/: Shared guidelines
- .workflow/: Phase artifacts
- AGENTS.md: Agent coordination

## Validation Tasks
1. Execute test suite completely
2. Check coverage meets targets
3. Verify architecture matches plan
4. Run security checks if applicable

## Output Format
{
  "status": "approved|revision_required|blocked",
  "tests_passing": true/false,
  "coverage": 85,
  "approved": true/false,
  "issues": [...]
}

## Parallel Execution
You may run in parallel with Cursor. Read from:
- .workflow/phases/{current}/
Do not overwrite files from other agents.
EOF

mkdir -p "$PROJECT_DIR/.gemini/agents"

cat > "$PROJECT_DIR/.gemini/agents/validator.json" << 'EOF'
{
  "name": "validator",
  "description": "Test and architecture validator",
  "capabilities": [
    "run_tests",
    "validate_architecture",
    "check_coverage",
    "run_security_checks"
  ]
}
EOF

log_done "Gemini CLI configured"

# Step 6: Create shared AGENTS.md
log_step "Creating shared AGENTS.md..."

cat > "$PROJECT_DIR/AGENTS.md" << 'EOF'
# Multi-Agent Orchestration - Shared Definitions

## Agents

### Claude Code (Orchestrator)
- Phase 1: Planning
- Phase 3: Implementation
- Responsibilities: Task breakdown, coding, test writing

### Cursor (Reviewer)
- Phase 2: Review plan quality
- Phase 4: Code quality review
- Responsibilities: Architecture validation, code review, quality gates

### Gemini (Validator)
- Phase 2: Architecture validation
- Phase 4: Test verification
- Responsibilities: Validation, testing, compliance checks

## Coordination Protocol

### Phase Handoffs
1. Previous agent writes output to `.workflow/phases/{num}/`
2. Current agent reads output and feedback
3. Current agent writes result to same directory
4. Orchestrator verifies completion

### Parallel Execution (Phases 2 & 4)
- Cursor and Gemini run simultaneously
- Each reads same input, writes to separate files
- Orchestrator merges feedback
- Both must approve before proceeding

### Approval Gates
- Phase 2: Both Cursor AND Gemini approval required
- Phase 4: Both Cursor AND Gemini approval required
- If either blocks: feedback sent to Claude for refinement

### Conflict Resolution
- If agents disagree: Priority = Architecture > Quality > Implementation
- Claude reads all feedback and makes final decision
- Decision logged in `.workflow/decision-log.md`

## Success Criteria
- All tests passing
- Both agents approved
- No active blockers
- PRODUCT.md criteria met
EOF

log_done "AGENTS.md created"

# Step 7: Create PRODUCT.md template
log_step "Creating PRODUCT.md template..."

cat > "$PROJECT_DIR/PRODUCT.md" << 'EOF'
# Product Vision & Development Roadmap

## Current Goal / Feature
[Describe the feature or goal]

### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

### Technical Requirements
- Framework/Language: 
- Performance Goals:
- Security Requirements:

### Architecture Notes
[Any key architectural decisions]

## Development Phases
This feature will go through 5 phases:

1. **Planning** - Break down into tasks (Claude) - ~5 min
2. **Test Design** - Validate plan (Cursor + Gemini) - ~10 min
3. **Implementation** - Code + tests (Claude) - ~20 min
4. **Verification** - Final review (Cursor + Gemini) - ~10 min
5. **Completion** - Merge and next steps - ~2 min

**Total Estimated Time**: ~50 minutes

## Phase Checklist
- [ ] Phase 1: Planning complete
- [ ] Phase 2: Reviews passed
- [ ] Phase 3: Implementation complete
- [ ] Phase 4: Verifications passed
- [ ] Phase 5: Merged to main

## How to Start
Update this file with your feature, then run:
\`\`\`bash
python .workflow/orchestrator.py --start
\`\`\`
EOF

log_done "PRODUCT.md created"

# Step 8: Create workflow state file
log_step "Creating workflow state..."

cat > "$PROJECT_DIR/.workflow/state.json" << 'EOF'
{
  "phase": "init",
  "phase_num": 0,
  "status": "ready_to_start",
  "created_at": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "last_updated": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "current_task": null,
  "completed_tasks": [],
  "active_blockers": []
}
EOF

log_done "Workflow state initialized"

# Step 9: Create schemas directory
log_step "Creating JSON schemas..."

cat > "$PROJECT_DIR/.workflow/schemas/plan-schema.json" << 'EOF'
{
  "title": "Plan Schema",
  "type": "object",
  "properties": {
    "phase": {"type": "string", "const": "planning"},
    "tasks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "title": {"type": "string"},
          "description": {"type": "string"},
          "dependencies": {"type": "array"},
          "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
          "test_strategy": {"type": "string"}
        },
        "required": ["id", "title", "dependencies"]
      }
    },
    "dependencies": {"type": "object"},
    "risks": {"type": "array"},
    "completion_criteria": {"type": "string"}
  },
  "required": ["phase", "tasks"]
}
EOF

cat > "$PROJECT_DIR/.workflow/schemas/feedback-schema.json" << 'EOF'
{
  "title": "Feedback Schema",
  "type": "object",
  "properties": {
    "overall_verdict": {"type": "string", "enum": ["approved", "revision_required", "blocked"]},
    "score": {"type": "number", "minimum": 0, "maximum": 100},
    "critical_issues": {"type": "array"},
    "warnings": {"type": "array"},
    "suggestions": {"type": "array"},
    "approved": {"type": "boolean"}
  },
  "required": ["overall_verdict", "approved"]
}
EOF

log_done "JSON schemas created"

# Step 10: Create Python orchestrator script
log_step "Creating orchestrator script..."

cat > "$PROJECT_DIR/.workflow/orchestrator.py" << 'PYEOF'
#!/usr/bin/env python3
"""
Multi-Agent Orchestrator
Manages workflow phases and agent coordination
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

class Orchestrator:
    def __init__(self, project_dir="."):
        self.project_dir = Path(project_dir).resolve()
        self.workflow_dir = self.project_dir / ".workflow"
        self.state_file = self.workflow_dir / "state.json"
        
    def load_state(self):
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"phase": "init", "phase_num": 0}
    
    def save_state(self, state):
        state["last_updated"] = datetime.utcnow().isoformat() + "Z"
        self.state_file.write_text(json.dumps(state, indent=2))
    
    def run_phase(self, phase_num):
        print(f"\n🚀 Starting Phase {phase_num}...")
        # Phase implementations will go here
        print(f"✅ Phase {phase_num} complete")
    
    def start(self):
        print("Starting multi-agent workflow...")
        state = self.load_state()
        
        # Phase 1: Planning
        self.run_phase(1)
        
        # Phase 2: Validation
        self.run_phase(2)
        
        # Phase 3: Implementation
        self.run_phase(3)
        
        # Phase 4: Verification
        self.run_phase(4)
        
        # Phase 5: Completion
        self.run_phase(5)
        
        print("\n✅ Workflow complete!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Agent Orchestrator")
    parser.add_argument("--start", action="store_true", help="Start workflow")
    parser.add_argument("--project-dir", default=".", help="Project directory")
    
    args = parser.parse_args()
    
    orchestrator = Orchestrator(args.project_dir)
    
    if args.start:
        orchestrator.start()
    else:
        print("Use --start to begin workflow")
PYEOF

chmod +x "$PROJECT_DIR/.workflow/orchestrator.py"

log_done "Orchestrator script created"

# Step 11: Create README
log_step "Creating README..."

cat > "$PROJECT_DIR/.workflow/README.md" << 'EOF'
# Multi-Agent Orchestration Workflow

This directory contains all coordination files for Claude Code, Cursor, and Gemini CLI.

## Directory Structure

```
.workflow/
├── phases/           # Phase-specific artifacts
│   ├── 01-planning/  # Planning outputs
│   ├── 02-test-design/
│   ├── 03-implementation/
│   ├── 04-verification/
│   └── 05-completion/
├── state.json        # Current workflow state
├── orchestrator.py   # Orchestration controller
└── logs/             # Workflow logs
```

## Quick Start

1. **Update PRODUCT.md** with your feature/goal
2. **Run orchestrator**:
   ```bash
   python .workflow/orchestrator.py --start
   ```
3. **Monitor progress** in .workflow/state.json

## Workflow Phases

| Phase | Agent | Task | Duration |
|-------|-------|------|----------|
| 1 | Claude Code | Plan breakdown | ~5 min |
| 2 | Cursor + Gemini | Validate plan | ~10 min |
| 3 | Claude Code | Implement + test | ~20 min |
| 4 | Cursor + Gemini | Final review | ~10 min |
| 5 | Orchestrator | Complete + next steps | ~2 min |

## Agent Roles

**Claude Code**: Planner and implementer
- Breaks down PRODUCT.md into tasks
- Writes tests and implementation

**Cursor**: Code reviewer
- Reviews plan quality
- Reviews code quality and architecture

**Gemini**: Validator
- Validates architecture
- Runs tests and verifies

## Using with CLI

```bash
# From project root, invoke agents directly
cd /path/to/project

# Claude Code planning
claude -p "Analyze PRODUCT.md and create plan" \
  --append-system-prompt-file=.claude/system.md

# Cursor review
cursor-agent -p "Review the plan at .workflow/phases/01-planning/plan.json" \
  --rules .cursor/rules

# Gemini validation
gemini -p "Validate plan at .workflow/phases/01-planning/plan.json" \
  -e validator-agent
```

## Monitoring

Check workflow progress:
```bash
cat .workflow/state.json
```

View phase outputs:
```bash
ls -la .workflow/phases/
```

Check coordination log:
```bash
tail .workflow/coordination.log
```
EOF

log_done "README created"

# Step 12: Create .gitignore entry
log_step "Creating .gitignore entries..."

if [ -f "$PROJECT_DIR/.gitignore" ]; then
    echo "" >> "$PROJECT_DIR/.gitignore"
fi

cat >> "$PROJECT_DIR/.gitignore" << 'EOF'

# Multi-agent workflow (keep structure, ignore temp files)
.workflow/logs/*.log
.workflow/phases/*/temp/
.workflow/blockers.json
EOF

log_done ".gitignore updated"

# Step 13: Initialize git if needed
log_step "Initializing git repository (if needed)..."

if [ ! -d "$PROJECT_DIR/.git" ]; then
    cd "$PROJECT_DIR"
    git init
    git add .
    git commit -m "chore: Initialize multi-agent orchestration"
    log_done "Git repository initialized"
else
    log_info "Git repository already exists"
fi

# Final summary
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Multi-Agent Setup Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "📂 Project: $PROJECT_DIR"
echo ""
echo "Next Steps:"
echo "1. Edit PRODUCT.md with your feature goal"
echo "2. Run: python .workflow/orchestrator.py --start"
echo "3. Monitor: cat .workflow/state.json"
echo ""
echo "Or use individual CLIs:"
echo "   Claude Code: cd $PROJECT_DIR && claude -p 'your prompt' --append-system-prompt-file=.claude/system.md"
echo "   Cursor: cd $PROJECT_DIR && cursor-agent -p 'your prompt' --rules .cursor/rules"
echo "   Gemini: cd $PROJECT_DIR && gemini -p 'your prompt' -e validator-agent"
echo ""
echo "Documentation: $PROJECT_DIR/.workflow/README.md"
echo ""
```

**Run the script**:
```bash
# Save script
cat > init-multi-agent.sh << 'SCRIPT_EOF'
[... script content above ...]
SCRIPT_EOF

# Make executable and run
chmod +x init-multi-agent.sh
./init-multi-agent.sh my-project

# Or one-liner (if hosted online)
curl -fsSL https://your-host/init-multi-agent.sh | bash -s -- my-project
```

---

## PRODUCT VISION WORKFLOW

### How to Structure Product Vision

**Product Vision reads the current feature/goal**, orchestrator processes through 5 phases:

```markdown
# Current Goal: Implement JWT Authentication Service

## What This Feature Does
Users can register, login, and authenticate via JWT tokens. Tokens refresh automatically.

## Acceptance Criteria
- [ ] User registration with email validation
- [ ] Login returns JWT tokens (access + refresh)
- [ ] Token refresh without re-login
- [ ] Tokens expire correctly
- [ ] Rate limiting prevents brute force
- [ ] Audit log records all auth events

## Technical Details
- Framework: Express.js + TypeScript
- Auth: JWT (HS256)
- Storage: PostgreSQL (users table)
- Tests: Jest with 85%+ coverage

## Architecture Decisions
- Separate auth service module
- Refresh tokens stored in DB (not JWT)
- Tokens in Authorization header
- Rate limiting via Redis

---

## Once Phase Complete

Update PRODUCT.md:
```markdown
# Previous: Implement JWT Authentication - ✅ COMPLETE

## Current Goal: Add Multi-Factor Authentication (MFA)

[Next feature details...]
```

Then re-run orchestrator for next feature iteration.
```

---

## IMPLEMENTATION PATTERNS & BEST PRACTICES

### Pattern 1: Claude Planning Breakdown

**Claude reads PRODUCT.md and creates structured plan**:

```bash
claude -p "
You are the planning agent.

Read PRODUCT.md (your north star).

Create a detailed plan with:
1. Task breakdown (each testable)
2. Dependency graph (which tasks block others)
3. Test strategy (how to validate each task)
4. Risk assessment
5. Completion criteria

Save output to: .workflow/phases/01-planning/plan.json
" --append-system-prompt-file=.claude/system.md
```

**Output structure Claude creates**:
```json
{
  "phase": "planning",
  "feature": "JWT Authentication",
  "tasks": [
    {
      "id": "t1",
      "title": "Create User model and schema",
      "description": "Define User with email, password (hashed), created_at fields",
      "dependencies": [],
      "complexity": "low",
      "test_strategy": "Unit tests for User creation and password hashing",
      "estimated_hours": 1
    },
    {
      "id": "t2",
      "title": "Implement token generation",
      "description": "Create JWT generation with HS256, access + refresh tokens",
      "dependencies": ["t1"],
      "complexity": "medium",
      "test_strategy": "Unit tests for token generation and expiration",
      "estimated_hours": 1.5
    }
  ],
  "dependency_graph": {
    "t2": ["t1"],
    "t3": ["t1"],
    "t4": ["t2", "t3"]
  },
  "risks": [
    "Token expiration edge cases",
    "Race conditions in refresh logic"
  ],
  "completion_criteria": "All tests pass, all tasks complete, no security issues"
}
```

### Pattern 2: Parallel Agent Validation

**Run Cursor and Gemini in parallel** (from orchestrator or manually):

```bash
# Terminal 1: Cursor reviews
cursor-agent -p "
Review plan at .workflow/phases/01-planning/plan.json

Check:
- Logical errors or gaps
- Missing edge cases
- Security concerns
- Test coverage strategy

Respond as JSON:
{
  \"verdict\": \"approved|revision_required|blocked\",
  \"score\": 0-100,
  \"issues\": [...]
}
" --rules .cursor/rules &

# Terminal 2: Gemini validates (in parallel)
gemini -p "
Validate plan at .workflow/phases/01-planning/plan.json

Check:
- Architecture alignment
- Design patterns
- Scalability
- Best practices

Respond as JSON:
{
  \"verdict\": \"approved|revision_required|blocked\",
  \"score\": 0-100,
  \"issues\": [...]
}
" -e validator-agent &

# Wait for both
wait
```

**Orchestrator merges feedback**:
```python
cursor_feedback = json.load(open(".workflow/phases/02-test-design/cursor-feedback.json"))
gemini_feedback = json.load(open(".workflow/phases/02-test-design/gemini-validation.json"))

if cursor_feedback["verdict"] != "approved" or gemini_feedback["verdict"] != "approved":
    print("⚠️  Feedback received - Claude to refinement")
    # Claude reads feedback and refines plan
else:
    print("✅ All reviews approved - move to implementation")
```

### Pattern 3: Test-First Implementation

**Claude implements tests before code**:

```bash
claude -p "
You are the implementation agent.

Your task: Implement 't1: Create User model'

STEP 1 - Write tests first (TDD):
- Test User creation
- Test password hashing
- Test validation

STEP 2 - Implement to pass tests:
- User model with fields
- Password hashing in constructor

STEP 3 - Run tests:
npm test -- spec/user.spec.ts

STEP 4 - Document decisions:
Write to .workflow/phases/03-implementation/implementation-log.md

Save test results to .workflow/phases/03-implementation/test-results.json
" --append-system-prompt-file=.claude/system.md
```

### Pattern 4: Coordination Via File System

**Agents communicate through files** (no direct API calls):

```
Phase 1 Output:
  ├─ plan.json ← Claude writes
  └─ PLAN.md

Phase 2 Inputs:
  ├─ plan.json ← Cursor reads
  ├─ plan.json ← Gemini reads

Phase 2 Outputs:
  ├─ cursor-feedback.json ← Cursor writes
  ├─ gemini-validation.json ← Gemini writes
  └─ consolidated-feedback.md ← Orchestrator merges

Phase 3 Inputs:
  ├─ plan.json ← Claude reads
  ├─ consolidated-feedback.md ← Claude reads and incorporates
  └─ (No context resets - file I/O only)

Phase 3 Output:
  ├─ implementation.md
  ├─ test-results.json
  └─ code changes (committed)
```

---

## REAL-WORLD EXAMPLE

### Feature: Build Authentication Service

**Step 1: Update PRODUCT.md**
```markdown
# Current Goal: Build JWT Authentication Service

## Feature
Users can register, login, and get JWT tokens that auto-refresh.

## Acceptance Criteria
- [ ] User registration (email validation)
- [ ] Login (returns access + refresh tokens)
- [ ] Token refresh (extends expiration)
- [ ] Token expiration handled correctly
- [ ] All tests pass (85%+ coverage)
- [ ] Code reviewed by Cursor and Gemini

## Tech Stack
- TypeScript + Express
- PostgreSQL
- Jest for testing

---

## Phase Checklist
- [ ] Phase 1: Planning
- [ ] Phase 2: Validation
- [ ] Phase 3: Implementation
- [ ] Phase 4: Verification
- [ ] Phase 5: Complete
```

**Step 2: Start Orchestrator**
```bash
cd auth-service
python .workflow/orchestrator.py --start
```

**Step 3: Monitor Phases**
```bash
# Check state
cat .workflow/state.json
{
  "phase": "planning",
  "phase_num": 1,
  "status": "running",
  "current_task": "claude-planning"
}

# After Phase 1 completes
cat .workflow/phases/01-planning/plan.json
{
  "phase": "planning",
  "tasks": [
    {"id": "t1", "title": "Create User model", "dependencies": []},
    {"id": "t2", "title": "Implement login", "dependencies": ["t1"]},
    {"id": "t3", "title": "Implement refresh", "dependencies": ["t1", "t2"]}
  ]
}

# Check Phase 2 feedback
cat .workflow/phases/02-test-design/consolidated-feedback.md
- Cursor: Approved ✅ (Code quality 95/100)
- Gemini: Approved ✅ (Architecture sound)
```

**Step 4: Implementation Happens**
```bash
# Phase 3: Claude implements
# - Writes test files to spec/
# - Implements src/auth/
# - Runs `npm test` (all passing)
# - Commits with messages like "[t1] Create User model"

# Watch progress
watch 'cat .workflow/phases/03-implementation/test-results.json'

# Final results
cat .workflow/phases/03-implementation/test-results.json
{
  "passed": 34,
  "failed": 0,
  "coverage": 86,
  "status": "READY_FOR_REVIEW"
}
```

**Step 5: Final Verification**
```bash
# Phase 4: Cursor + Gemini final review
# - Cursor: Code quality review ✅
# - Gemini: Test verification ✅

# Check approvals
cat .workflow/phases/04-verification/ready-to-merge.json
{
  "cursor_approved": true,
  "gemini_approved": true,
  "status": "APPROVED_FOR_MERGE",
  "approvals": ["cursor", "gemini"]
}
```

**Step 6: Complete & Next Feature**
```bash
# Phase 5: Completion
# - Feature merged to main
# - Update PRODUCT.md with next goal

# Next feature
cat PRODUCT.md
# Current Goal: Add Multi-Factor Authentication (MFA)
# [... details ...]

# Re-run for next feature
python .workflow/orchestrator.py --start
```

---

## TROUBLESHOOTING & ADVANCED PATTERNS

### Issue: "Agent lost context between phases"

**Solution**: All context is file-based. Agents read:
```bash
.workflow/phases/{current}/output.json  # Previous phase output
.workflow/phases/{current}/feedback.json  # Feedback from other agents
PRODUCT.md  # Always read this first
.rules/  # Shared rules
```

### Issue: "Agents making different decisions"

**Solution**: Ensure shared rules in AGENTS.md are consistent:
```bash
# All agents read AGENTS.md and follow same protocol
cat AGENTS.md  # Check agent definitions are aligned

# If Claude disagrees with Cursor:
# 1. Claude reads both feedbacks
# 2. Logs decision in .workflow/decision-log.md
# 3. Explains reasoning
```

### Issue: "Running agents in parallel, but getting conflicts"

**Solution**: Each agent writes to separate files:
```bash
# ✅ CORRECT: Parallel execution
cursor-agent -p "..." > .workflow/phases/02/cursor-feedback.json &
gemini -p "..." > .workflow/phases/02/gemini-validation.json &
wait

# ❌ WRONG: Both writing to same file
cursor-agent -p "..." > .workflow/phases/02/feedback.json &
gemini -p "..." > .workflow/phases/02/feedback.json &  # Conflict!
```

### Advanced: Custom MCP Servers for Rich Context

```python
# Custom MCP server that exposes project artifacts as tools
# All agents can access via MCP

from mcp import Server

server = Server("project-context")

@server.expose_tool("read_product_vision")
def read_product_vision():
    """Get current PRODUCT.md vision"""
    return Path("PRODUCT.md").read_text()

@server.expose_tool("read_phase_output")
def read_phase_output(phase_num: int):
    """Get output from previous phase"""
    phase_dir = Path(f".workflow/phases/{phase_num:02d}-*/")
    return (phase_dir / "output.json").read_text()

@server.expose_tool("get_agent_feedback")
def get_agent_feedback(phase_num: int, agent_name: str):
    """Get specific agent's feedback"""
    return Path(f".workflow/phases/{phase_num:02d}-*/{agent_name}-feedback.json").read_text()
```

### Advanced: Distributed Coordination with Redis

For multi-machine workflows:

```python
import redis

class DistributedOrchestrator:
    def __init__(self):
        self.redis = redis.Redis(host='localhost')
    
    def save_phase_output(self, phase_num, data):
        # Save to both file system and Redis
        Path(f".workflow/phases/{phase_num:02d}").mkdir(exist_ok=True)
        Path(f".workflow/phases/{phase_num:02d}/output.json").write_text(json.dumps(data))
        
        # Also save to Redis for distributed access
        self.redis.set(f"phase:{phase_num}:output", json.dumps(data))
    
    def wait_for_approvals(self, phase_num):
        # Agents write approvals to Redis
        # Orchestrator polls redis
        cursor_approved = self.redis.get(f"phase:{phase_num}:cursor:approved")
        gemini_approved = self.redis.get(f"phase:{phase_num}:gemini:approved")
        
        return cursor_approved == b"true" and gemini_approved == b"true"
```

---

## SUMMARY & NEXT STEPS

### What You Now Have

✅ **Shared Project Context**: All agents in same folder inheriting identical context
✅ **Five-Phase Workflow**: Vision → Plan → Test → Implement → Verify
✅ **Parallel Execution**: Cursor + Gemini validation simultaneously
✅ **File-System Coordination**: No API calls, filesystem as state
✅ **Shared Rules**: AGENTS.md, RULES/, configuration consistency
✅ **Initialization Script**: Ready-to-go setup for any project

### For Your Coding Agent

Provide:
1. **init-multi-agent.sh** script (above)
2. **AGENTS.md** (shared definitions)
3. **.claude/system.md, .cursor/rules, .gemini/GEMINI.md** (config templates)
4. **orchestrator.py** (phase management - scaffolding only)
5. **This documentation** (use cases and patterns)

Agent should:
- Expand orchestrator.py with phase implementations
- Create hooks for additional validation
- Add MCP servers if needed
- Customize prompts per project

### Production Readiness Checklist

- [ ] All three CLIs installed and in PATH
- [ ] `.workflow/` directory in git (track artifacts)
- [ ] PRODUCT.md updated with first feature
- [ ] Tested locally with each CLI
- [ ] Error handling in orchestrator
- [ ] Logging configured
- [ ] Token usage monitoring
- [ ] CI/CD integration (optional)

---

## REFERENCES & RESOURCES

1. **Claude Code Documentation**: https://code.claude.com/docs
   - Hooks, SubAgents, MCP integration
2. **Cursor Multi-Agent**: https://forums.cursor.com/multi-agents
   - Role-based agent coordination
3. **Gemini CLI**: https://gemini.com/cli
   - Task queues, parallel execution, containers
4. **File-System-as-State Pattern**: https://aipositive.substack.com/gemini-multi-agent
   - Stateless agents with persistent file coordination
5. **Multi-Agent Orchestration Research**: https://github.com/anthropics/multi-agent-patterns
   - Latest patterns and implementations

---

**End of Documentation**

This is a comprehensive, production-ready guide for true multi-agent orchestration with shared project context. All three CLIs run as subprocesses in the same folder, coordinating through files and shared configuration.
