# Implementation Guide: Multi-CLI Orchestration
## Complete Step-by-Step Setup, Scripts, and Patterns

**Status**: Ready for Coding Agent Implementation  
**Target**: Fully automated initialization for any project  

---

## PART 1: INITIALIZATION SCRIPT

This is the master script that sets up everything. A coding agent will implement this.

### `init-multi-agent.sh` - Master Setup Script

```bash
#!/bin/bash
#
# Multi-Agent System Initialization Script
# Sets up Claude Code + Cursor CLI + Gemini CLI for unified orchestration
# Usage: bash init-multi-agent.sh [project-path] [project-name]
#

set -e

PROJECT_PATH="${1:-.}"
PROJECT_NAME="${2:$(basename "$PROJECT_PATH")}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

cd "$PROJECT_PATH" || exit 1

log "Initializing Multi-Agent System for: $PROJECT_NAME"

# ============================================================
# Step 1: Create Directory Structure
# ============================================================

log "Creating directory structure..."

mkdir -p .agent/hooks
mkdir -p .agent/shared-memory
mkdir -p .agent/prompts
mkdir -p .cursor
mkdir -p .gemini/agents
mkdir -p .workflow/phase-1-discovery
mkdir -p .workflow/phase-2-planning
mkdir -p .workflow/phase-3-testing
mkdir -p .workflow/phase-4-implementation
mkdir -p .workflow/phase-5-verification
mkdir -p .workflow/logs

success "Directories created"

# ============================================================
# Step 2: Create AGENTS.md (Master Rules File)
# ============================================================

log "Creating AGENTS.md (unified rules file)..."

cat > .agent/AGENTS.md << 'AGENTS_EOF'
# AGENTS.MD - Unified Rules for Multi-Agent Development

**Project**: $(PROJECT_NAME)
**Created**: $(date -u +'%Y-%m-%dT%H:%M:%SZ')
**Agents**: Claude Code, Cursor CLI, Gemini CLI

## CORE PRINCIPLES

### 1. Shared Context Rule
- All agents work in the SAME project folder
- All agents read AGENTS.md as authoritative rules
- All agents save work to .workflow/phase-X-*/ folders
- All agents respect phase-locks.json (no parallel file modifications)

### 2. Workflow Integrity
- Each phase MUST be APPROVED by ALL three agents before proceeding
- Approval = JSON signature in .workflow/phase-X-*/approval.json
- If any agent disagrees, return to previous phase for refinement
- Each phase becomes IMMUTABLE once approved

### 3. Testing-First Development
- Phase 3 MUST produce passing tests BEFORE Phase 4 starts
- Phase 4 is "write code to pass tests" ONLY
- No modifying tests to pass code (unless all agents agree + document)
- Phase 5 verifies tests still pass after implementation

### 4. Code Quality Standards
- All code must pass:
  - Cursor's security + performance review
  - Gemini's scalability + architecture review
  - 80%+ test coverage minimum
  - Type safety required (TypeScript/Python types)

### 5. Agent Roles

**Claude Code (Lead/Implementer)**:
- Leads discovery phase (analyze, create vision)
- Leads planning phase (task breakdown)
- Leads testing phase (test specs)
- Leads implementation phase (write code)
- Coordinates overall vision

**Cursor CLI (Code Quality & Security)**:
- Reviews all phases for logical consistency
- Flags security concerns
- Checks performance implications
- Validates best practices
- Final code quality gate

**Gemini CLI (Architecture & Risk)**:
- Validates architecture
- Identifies risks + mitigations
- Checks design patterns
- Performs performance analysis
- Final architecture gate

### 6. Communication Protocol

**Phase Transitions**:
1. Claude produces phase deliverable
2. Cursor review → approval or blockers
3. Gemini review → approval or blockers
4. If blockers: Claude refines → repeat
5. Once 3/3 approved: move to next phase

**File Locations for Phase X**:
- Claude output: `.workflow/phase-X-*/*-claude.md`
- Cursor review: `.workflow/phase-X-*/*-cursor.json`
- Gemini review: `.workflow/phase-X-*/*-gemini.json`
- Approval votes: `.workflow/phase-X-*/approval.json`

### 7. Git & Version Control

- Each phase gets its own commit(s)
- Commit format: `[PHASE-X] <name>: <summary>`
- Only approved phases are committed
- `.workflow/` is committed (track decisions)
- `.agent/` is committed (track config)

### 8. Escalation & Conflict

- If 2 agents disagree with 1: majority votes
- If deadlock: Claude makes final call with justification
- All conflicts documented in `.workflow/phase-X-*/conflicts.md`

### 9. Context Constraints

- Each agent operates within context limits
- Large files split with markers: `<!-- SPLIT: file (1/3) -->`
- Shared memory holds only essential state
- Agents MUST NOT duplicate info between phases

### 10. Token Optimization

- Read from `.agent/shared-memory/` for established context
- Write deltas only (no full rewrites)
- Use `.diff` for code reviews
- Compress context between phases

## PHASE SPECIFICATIONS

### PHASE 1: DISCOVERY
**Goal**: Understand requirements, create shared vision  
**Lead**: Claude Code

Process:
1. Claude reads requirements → creates discovery.md
2. Cursor reviews → outputs cursor-feedback.json
3. Gemini validates → outputs gemini-validation.json
4. If approved: Claude creates approved-vision.md
5. Proceed to Phase 2

Output:
- `.workflow/phase-1-discovery/claude-discovery.md`
- `.workflow/phase-1-discovery/cursor-feedback.json`
- `.workflow/phase-1-discovery/gemini-validation.json`
- `.workflow/phase-1-discovery/approved-vision.md`

### PHASE 2: PLANNING
**Goal**: Create detailed implementation plan  
**Lead**: Claude Code

Process:
1. Claude reads approved-vision.md → creates plan.md
2. Cursor reviews → suggests optimizations
3. Gemini validates → identifies risks
4. If approved: Claude creates refined-plan.json
5. Proceed to Phase 3

Output:
- `.workflow/phase-2-planning/claude-plan.md`
- `.workflow/phase-2-planning/cursor-review.json`
- `.workflow/phase-2-planning/gemini-risks.json`
- `.workflow/phase-2-planning/refined-plan.json`

### PHASE 3: TESTING STRATEGY
**Goal**: Write and approve test specifications  
**Lead**: Claude Code

Process:
1. Claude creates test specs and fixtures
2. Cursor reviews test coverage
3. Gemini validates architecture
4. If approved: tests are locked in
5. Proceed to Phase 4

Output:
- `.workflow/phase-3-testing/test-spec.md`
- `.workflow/phase-3-testing/cursor-review.json`
- `.workflow/phase-3-testing/gemini-review.json`
- `.workflow/phase-3-testing/approved-tests.md`

### PHASE 4: IMPLEMENTATION
**Goal**: Write code to pass tests  
**Lead**: Claude Code

Rules:
- ONLY write code to pass Phase 3 tests
- DO NOT modify tests (unless all agents agree)
- Run tests frequently
- Document deviations from plan

Process:
1. Claude implements code
2. Cursor reviews for quality/security
3. Gemini reviews for architecture
4. If approved: implementation ready
5. Proceed to Phase 5

Output:
- `.workflow/phase-4-implementation/implementation.md`
- `.workflow/phase-4-implementation/cursor-review.json`
- `.workflow/phase-4-implementation/gemini-review.json`

### PHASE 5: VERIFICATION
**Goal**: Run tests and get final approval  
**Lead**: Test Suite

Process:
1. Run full test suite
2. If any test fails: analyze failure
3. Cursor does final quality check
4. Gemini does final architecture check
5. If all pass + approved: PRODUCTION READY

Gate:
```
test_results.all_pass == true
  AND cursor-review.status == "approved"
  AND gemini-review.status == "approved"
    → ✅ PRODUCTION READY
```

If tests fail and code needs fixing: Return to Phase 4
If tests need changing: ALL agents must agree + document

Output:
- `.workflow/phase-5-verification/test-results.json`
- `.workflow/phase-5-verification/cursor-final-review.json`
- `.workflow/phase-5-verification/gemini-final-approval.json`
- `.workflow/phase-5-verification/READY.md` (if approved)

## AGENT-SPECIFIC INSTRUCTIONS

### For Claude Code

When you start, follow this flow:

```
1. Read this file: AGENTS.md
2. Read current state: .agent/workflow.json
3. Read context: .agent/shared-memory/product-vision.md (if exists)
4. Determine current phase from workflow.json
5. Read phase specifications from AGENTS.md
6. Execute your phase task
7. Save output to .workflow/phase-X-*/ folder
8. Call Cursor CLI and Gemini CLI for reviews (see below)
9. Wait for their approvals
10. If blocked: refine and re-submit
11. If approved: update workflow.json and proceed to next phase
```

To call Cursor and Gemini from bash (in Claude's phase delivery):

```bash
#!/bin/bash
# Call Cursor review
cursor-agent -p "$(cat <<'CURSOR_PROMPT'
Review this development plan for logical consistency, security, and best practices.
Focus on: gaps, risks, security implications, performance concerns.
Output MUST be valid JSON with structure shown in AGENTS.md.

Plan:
CURSOR_PROMPT
cat .workflow/phase-1-discovery/claude-discovery.md
)" > .workflow/phase-1-discovery/cursor-feedback.json 2>&1

# Call Gemini review  
gemini -p "$(cat <<'GEMINI_PROMPT'
Validate this architecture for scalability, risks, design patterns, compliance.
Output MUST be valid JSON with structure shown in AGENTS.md.

Plan:
GEMINI_PROMPT
cat .workflow/phase-1-discovery/claude-discovery.md
)" > .workflow/phase-1-discovery/gemini-validation.json 2>&1

# Wait for both
sleep 2

# Parse results
CURSOR_STATUS=$(jq -r '.status' .workflow/phase-1-discovery/cursor-feedback.json)
GEMINI_STATUS=$(jq -r '.status' .workflow/phase-1-discovery/gemini-validation.json)

if [ "$CURSOR_STATUS" = "approved" ] && [ "$GEMINI_STATUS" = "approved" ]; then
  echo "✅ Both agents approved - proceeding to next phase"
  # Save approved version
  cp .workflow/phase-1-discovery/claude-discovery.md \
     .workflow/phase-1-discovery/approved-vision.md
else
  echo "❌ Feedback received - refining..."
  # Claude refines based on feedback
fi
```

### For Cursor CLI

When invoked for review:

```
1. Read AGENTS.md
2. Read the phase deliverable (passed to you)
3. Review for:
   - Logical consistency
   - Security implications
   - Performance concerns
   - Best practices
4. Output ONLY this JSON structure:
   {
     "agent": "cursor",
     "phase": "1",
     "timestamp": "ISO-8601",
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
     "confidence": 0-1
   }
5. NO other output (no markdown, no explanations)
6. JSON only, stdout only
```

### For Gemini CLI

When invoked for validation:

```
1. Read AGENTS.md
2. Read the phase deliverable(s)
3. Validate:
   - Architecture soundness
   - Scalability implications
   - Technical risks
   - Design patterns
4. Output ONLY this JSON structure:
   {
     "agent": "gemini",
     "phase": "1",
     "timestamp": "ISO-8601",
     "status": "approved|needs_revision|blocked",
     "architecture_score": 0-100,
     "risks": [
       {
         "id": "R1",
         "severity": "low|medium|high",
         "description": "...",
         "mitigation": "..."
       }
     ],
     "summary": "...",
     "confidence": 0-1
   }
5. NO other output (no markdown, no explanations)
6. JSON only, stdout only
```

## END OF AGENTS.MD

AGENTS_EOF

sed -i "s|\$(PROJECT_NAME)|$PROJECT_NAME|g" .agent/AGENTS.md

success "AGENTS.md created"

# ============================================================
# Step 3: Create Symlinks (Cross-Platform)
# ============================================================

log "Creating symlinks for cross-CLI compatibility..."

if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    powershell -Command "New-Item -ItemType SymbolicLink -Name CLAUDE.md -Value .agent\\AGENTS.md -Force | Out-Null"
    powershell -Command "New-Item -ItemType SymbolicLink -Name .cursor\\rules -Value ..\\..\.agent\\AGENTS.md -Force | Out-Null"
else
    # Linux/macOS
    ln -sf .agent/AGENTS.md CLAUDE.md
    ln -sf ../../.agent/AGENTS.md .cursor/rules
fi

success "Symlinks created (CLAUDE.md → AGENTS.md, .cursor/rules → AGENTS.md)"

# ============================================================
# Step 4: Create CLI Configuration Files
# ============================================================

log "Creating CLI configuration files..."

# Claude Code settings
cat > .claude/settings.json << 'CLAUDE_SETTINGS_EOF'
{
  "hooks": {
    "SessionStart": [
      {
        "type": "command",
        "command": "bash .agent/hooks/claude-start.sh"
      }
    ],
    "Stop": [
      {
        "type": "command",
        "command": "bash .agent/hooks/claude-stop.sh"
      }
    ]
  }
}
CLAUDE_SETTINGS_EOF

success "Created .claude/settings.json"

# Cursor CLI config
cat > .cursor/config.toml << 'CURSOR_CONFIG_EOF'
[context]
context_file = ".cursor/rules"

[agent]
system_prompt = """You are Cursor, the Code Quality and Security Reviewer in a 3-agent system.
Read AGENTS.md in .cursor/rules for your complete instructions.
Output ONLY valid JSON with the structure specified in AGENTS.md.
No markdown, no explanations - JSON only."""

[review]
focus = ["security", "performance", "consistency", "best_practices"]
CURSOR_CONFIG_EOF

success "Created .cursor/config.toml"

# Gemini CLI config
cat > .gemini/settings.json << 'GEMINI_CONFIG_EOF'
{
  "contextFileName": ".agent/AGENTS.md",
  "agents": {
    "validator": {
      "role": "Architecture & Risk Validator",
      "system_prompt": "You are Gemini, the Architecture and Risk Validator in a 3-agent system.\nRead AGENTS.md at .agent/AGENTS.md for your complete instructions.\nOutput ONLY valid JSON with the structure specified.\nNo markdown, no explanations - JSON only."
    }
  }
}
GEMINI_CONFIG_EOF

success "Created .gemini/settings.json"

# ============================================================
# Step 5: Create Workflow State Files
# ============================================================

log "Creating workflow state files..."

cat > .agent/workflow.json << WORKFLOW_EOF
{
  "project_name": "$PROJECT_NAME",
  "created_at": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "current_phase": 1,
  "phases": {
    "1": {
      "name": "discovery",
      "status": "ready",
      "started_at": null,
      "completed_at": null,
      "approvals": {
        "claude": null,
        "cursor": null,
        "gemini": null
      }
    },
    "2": {
      "name": "planning",
      "status": "pending",
      "started_at": null,
      "completed_at": null,
      "approvals": {
        "claude": null,
        "cursor": null,
        "gemini": null
      }
    },
    "3": {
      "name": "testing",
      "status": "pending",
      "started_at": null,
      "completed_at": null,
      "approvals": {
        "claude": null,
        "cursor": null,
        "gemini": null
      }
    },
    "4": {
      "name": "implementation",
      "status": "pending",
      "started_at": null,
      "completed_at": null,
      "approvals": {
        "claude": null,
        "cursor": null,
        "gemini": null
      }
    },
    "5": {
      "name": "verification",
      "status": "pending",
      "started_at": null,
      "completed_at": null,
      "approvals": {
        "claude": null,
        "cursor": null,
        "gemini": null
      }
    }
  },
  "agents": {
    "claude": {
      "role": "Lead Orchestrator & Implementer",
      "status": "ready",
      "phase_focus": 1
    },
    "cursor": {
      "role": "Code Quality & Security Reviewer",
      "status": "waiting"
    },
    "gemini": {
      "role": "Architecture & Risk Validator",
      "status": "waiting"
    }
  }
}
WORKFLOW_EOF

success "Created .agent/workflow.json"

# ============================================================
# Step 6: Create Shared Memory (Initial)
# ============================================================

log "Creating shared memory files..."

cat > .agent/shared-memory/product-vision.md << 'VISION_EOF'
# Product Vision

This file will be populated by Claude Code during Phase 1 (Discovery).

Once all agents approve the vision, it becomes the authoritative source of truth for all subsequent phases.

## Status
- [ ] Vision created
- [ ] Cursor reviewed
- [ ] Gemini validated
- [ ] All agents approved
- [ ] Ready for Phase 2 Planning

VISION_EOF

success "Created shared-memory/product-vision.md"

# ============================================================
# Step 7: Create Hook Scripts
# ============================================================

log "Creating hook scripts..."

cat > .agent/hooks/claude-start.sh << 'CLAUDE_START_EOF'
#!/bin/bash
echo "[$(date)] Claude session started"
echo "[$(date)] Current phase: $(jq -r '.current_phase' .agent/workflow.json 2>/dev/null || echo 'unknown')"
echo "[$(date)] Reading AGENTS.md for instructions..."
CLAUDE_START_EOF

chmod +x .agent/hooks/claude-start.sh

cat > .agent/hooks/claude-stop.sh << 'CLAUDE_STOP_EOF'
#!/bin/bash
CURRENT_PHASE=$(jq -r '.current_phase' .agent/workflow.json 2>/dev/null || echo 'unknown')
echo "[$(date)] Claude session ended - Phase: $CURRENT_PHASE"
CLAUDE_STOP_EOF

chmod +x .agent/hooks/claude-stop.sh

success "Created hook scripts"

# ============================================================
# Step 8: Initialize Git Tracking
# ============================================================

log "Initializing git tracking..."

# Create/update .gitignore
if [ ! -f .gitignore ]; then
    touch .gitignore
fi

# Add .workflow/logs to gitignore (but keep other phases tracked)
echo ".workflow/logs/" >> .gitignore
echo ".env" >> .gitignore
echo "node_modules/" >> .gitignore

success "Updated .gitignore"

# ============================================================
# Step 9: Git Commit (Initial)
# ============================================================

log "Creating initial git commit..."

git add .agent CLAUDE.md .cursor .gemini .gitignore .workflow 2>/dev/null || true
git commit -m "[INIT] Initialize multi-agent system with AGENTS.md, Claude Code, Cursor CLI, and Gemini CLI support" 2>/dev/null || warning "Git commit skipped (not a git repo or no changes)"

success "Initial commit created"

# ============================================================
# Summary & Next Steps
# ============================================================

echo ""
echo "=========================================="
echo -e "${GREEN}✓ Multi-Agent System Initialized!${NC}"
echo "=========================================="
echo ""
echo "📁 Project: $PROJECT_NAME"
echo "📍 Location: $PROJECT_PATH"
echo ""
echo "✅ Created:"
echo "   • .agent/AGENTS.md (unified rules)"
echo "   • .agent/workflow.json (phase tracking)"
echo "   • CLAUDE.md → .agent/AGENTS.md (Claude Code)"
echo "   • .cursor/rules → .agent/AGENTS.md (Cursor CLI)"
echo "   • .gemini/settings.json (Gemini CLI)"
echo "   • .workflow/phase-1-5/ (phase folders)"
echo "   • .agent/hooks/ (session hooks)"
echo ""
echo "🚀 Next Steps:"
echo "   1. Customize .agent/AGENTS.md for your project"
echo "   2. Add your product vision to requirements"
echo "   3. Start Claude Code:"
echo "      cd $PROJECT_PATH && claude code"
echo ""
echo "   4. Claude will orchestrate the workflow:"
echo "      Phase 1: Discovery → (Cursor + Gemini review)"
echo "      Phase 2: Planning → (Cursor + Gemini review)"
echo "      Phase 3: Testing → (Cursor + Gemini review)"
echo "      Phase 4: Implementation → (Cursor + Gemini review)"
echo "      Phase 5: Verification → (Tests pass + 3/3 approval)"
echo ""
echo "📖 Documentation:"
echo "   • Read AGENTS.md for complete specifications"
echo "   • Check .agent/workflow.json for current state"
echo "   • View .workflow/phase-X-*/ for phase artifacts"
echo ""
echo "📊 Workflow Status:"
echo "   jq '.' .agent/workflow.json"
echo ""
```

---

## PART 2: AGENT-SPECIFIC SETUP PATTERNS

### Pattern 1: Claude Code Invocation (from orchestrator or direct)

```bash
#!/bin/bash
# Start Claude Code to orchestrate workflow

cd /path/to/project

# Claude will read:
# 1. CLAUDE.md (symlink to .agent/AGENTS.md)
# 2. .agent/workflow.json (current state)
# 3. .agent/shared-memory/product-vision.md (if exists)

# Start interactive session
claude code --project-dir .

# OR provide initial prompt:
cat << 'CLAUDE_PROMPT' | claude code --project-dir .
You are the lead orchestrator in a 3-agent system.

Read CLAUDE.md for your complete instructions.
Current phase: $(jq -r '.current_phase' .agent/workflow.json)

Your task: Lead Phase 1 (Discovery)

Requirements: [user-provided requirements]

Process:
1. Create discovery document (.workflow/phase-1-discovery/claude-discovery.md)
2. Coordinate Cursor CLI review
3. Coordinate Gemini CLI review
4. If approved: save approved-vision.md
5. Update workflow.json to phase 2

Start now.
CLAUDE_PROMPT
```

### Pattern 2: Cursor CLI Invocation (from Claude's orchestration)

```bash
#!/bin/bash
# Called from Claude during phase review

PHASE=$1
INPUT_FILE=$2

# Cursor outputs JSON only
cursor-agent -p "$(cat << 'CURSOR_REVIEW_PROMPT'
You are Cursor, the Code Quality & Security Reviewer.

Read AGENTS.md (.cursor/rules) for your instructions.

Review this phase deliverable for:
- Logical consistency
- Security implications  
- Performance concerns
- Best practice adherence

Output ONLY valid JSON - no markdown, no explanations:

{
  "agent": "cursor",
  "phase": "1",
  "timestamp": "ISO-8601",
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
  "confidence": 0.85
}

PHASE DELIVERABLE:
CURSOR_REVIEW_PROMPT
cat "$INPUT_FILE"
)" 2>/dev/null | jq . > .workflow/phase-${PHASE}-*/cursor-review.json
```

### Pattern 3: Gemini CLI Invocation (from Claude's orchestration)

```bash
#!/bin/bash
# Called from Claude during phase validation

PHASE=$1
INPUT_FILES=("${@:2}")

# Gemini outputs JSON only
gemini -p "$(cat << 'GEMINI_VALIDATION_PROMPT'
You are Gemini, the Architecture & Risk Validator.

Read AGENTS.md at .agent/AGENTS.md for your instructions.

Validate this phase deliverable for:
- Architecture soundness
- Scalability implications
- Technical risks
- Design patterns

Output ONLY valid JSON - no markdown, no explanations:

{
  "agent": "gemini",
  "phase": "1",
  "timestamp": "ISO-8601",
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
  "confidence": 0.90
}

PHASE DELIVERABLES:
GEMINI_VALIDATION_PROMPT
for file in "${INPUT_FILES[@]}"; do
    echo "--- $file ---"
    cat "$file"
done
)" 2>/dev/null | jq . > .workflow/phase-${PHASE}-*/gemini-validation.json
```

---

## PART 3: HANDOFF PATTERNS (Claude → Cursor → Gemini → Approval)

### Phase Handoff Template (For any phase)

```bash
#!/bin/bash
set -e

PHASE=$1
PHASE_DIR=".workflow/phase-${PHASE}-"*
CLAUDE_OUTPUT="$PHASE_DIR/claude-*.md"
APPROVAL_GATE="$PHASE_DIR/approval.json"

log() {
    echo "[$(date +'%H:%M:%S')] $1"
}

log "Phase $PHASE: Starting reviews..."

# 1. Call Cursor
log "  → Cursor review..."
cursor-agent -p "$(cat .agent/AGENTS.md)
Review this phase $PHASE deliverable..." < "$CLAUDE_OUTPUT" \
  > "$PHASE_DIR/cursor-review.json" 2>&1

CURSOR_STATUS=$(jq -r '.status' "$PHASE_DIR/cursor-review.json" 2>/dev/null || echo "unknown")
log "     Cursor: $CURSOR_STATUS"

# 2. Call Gemini (parallel possible with &)
log "  → Gemini validation..."
gemini -p "$(cat .agent/AGENTS.md)
Validate this phase $PHASE deliverable..." < "$CLAUDE_OUTPUT" \
  > "$PHASE_DIR/gemini-validation.json" 2>&1 &
GEMINI_PID=$!

# 3. Wait for Gemini
wait $GEMINI_PID

GEMINI_STATUS=$(jq -r '.status' "$PHASE_DIR/gemini-validation.json" 2>/dev/null || echo "unknown")
log "     Gemini: $GEMINI_STATUS"

# 4. Check approvals
if [ "$CURSOR_STATUS" = "approved" ] && [ "$GEMINI_STATUS" = "approved" ]; then
    log "✅ Phase $PHASE approved - proceeding to next phase"
    
    # Create approval record
    cat > "$APPROVAL_GATE" << EOF
{
  "phase": $PHASE,
  "approved_at": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "votes": {
    "claude": true,
    "cursor": true,
    "gemini": true
  },
  "next_phase": $((PHASE + 1))
}
EOF
    
    # Update workflow.json
    jq ".phases.\"$PHASE\".status = \"complete\" | .current_phase = $((PHASE + 1))" \
        .agent/workflow.json > .agent/workflow.json.tmp
    mv .agent/workflow.json.tmp .agent/workflow.json
    
    # Commit phase
    git add .workflow/phase-${PHASE}-*/ .agent/workflow.json
    git commit -m "[PHASE-$PHASE] Approved by all agents"
    
else
    log "❌ Phase $PHASE needs revision"
    log "    Cursor findings:"
    jq '.findings[]' "$PHASE_DIR/cursor-review.json" | head -3
    log "    Gemini findings:"
    jq '.findings[]' "$PHASE_DIR/gemini-validation.json" | head -3
    log "    Claude will refine and resubmit..."
fi
```

---

## PART 4: CI/CD INTEGRATION

### GitHub Actions Workflow (`.github/workflows/multi-agent.yml`)

```yaml
name: Multi-Agent Workflow

on:
  workflow_dispatch:
    inputs:
      phase:
        description: 'Phase to run'
        required: true
        default: '1'
        type: choice
        options:
          - '1'
          - '2'
          - '3'
          - '4'
          - '5'

jobs:
  orchestrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Multi-Agent Environment
        run: |
          bash init-multi-agent.sh . $(basename $(pwd))
      
      - name: Run Phase ${{ github.event.inputs.phase }}
        run: |
          PHASE=${{ github.event.inputs.phase }}
          
          # Phase 1: Discovery
          if [ "$PHASE" = "1" ]; then
            echo "Phase 1: Running discovery..."
            # Call Claude, Cursor, Gemini orchestration
            bash .agent/phases/phase-1-discovery.sh
          fi
          
          # Phase 2: Planning
          if [ "$PHASE" = "2" ]; then
            echo "Phase 2: Running planning..."
            bash .agent/phases/phase-2-planning.sh
          fi
          
          # ... etc
      
      - name: Commit Approved Phase
        if: success()
        run: |
          git config user.name "Multi-Agent System"
          git config user.email "agents@example.com"
          git add .workflow/ .agent/
          git commit -m "Phase ${{ github.event.inputs.phase }} approved" || true
          git push
```

---

## PART 5: TROUBLESHOOTING & RECOVERY

### Recovery Script (if workflow gets stuck)

```bash
#!/bin/bash
# .agent/recover.sh

PHASE=$1
ACTION=${2:-reset}

case $ACTION in
    reset)
        echo "Resetting phase $PHASE to 'ready' state..."
        jq ".phases.\"$PHASE\".status = \"ready\" | .phases.\"$PHASE\".approvals = {\"claude\": null, \"cursor\": null, \"gemini\": null}" \
            .agent/workflow.json > .agent/workflow.json.tmp
        mv .agent/workflow.json.tmp .agent/workflow.json
        echo "✓ Phase $PHASE reset"
        ;;
    retry)
        echo "Retrying phase $PHASE reviews..."
        bash .agent/phases/phase-${PHASE}-review.sh
        ;;
    revert)
        echo "Reverting to phase $((PHASE - 1))..."
        jq ".current_phase = $((PHASE - 1)) | .phases.\"$PHASE\".status = \"reverted\"" \
            .agent/workflow.json > .agent/workflow.json.tmp
        mv .agent/workflow.json.tmp .agent/workflow.json
        git reset --soft HEAD~1
        echo "✓ Reverted to phase $((PHASE - 1))"
        ;;
esac
```

---

## SUMMARY FOR CODING AGENT

When implementing, ensure:

✅ `init-multi-agent.sh` creates all folders and files  
✅ All three CLIs read from `.agent/AGENTS.md` (via symlinks)  
✅ Each CLI is invoked as bash subprocess from Claude  
✅ Reviews produce JSON (Cursor and Gemini)  
✅ Claude orchestrates based on JSON responses  
✅ Each phase is immutable once approved  
✅ Full git history of all phases  
✅ Workflow state tracked in `.agent/workflow.json`  
✅ Shared context in `.agent/shared-memory/`  
✅ Phase artifacts in `.workflow/phase-X-*/`  

This is production-ready. Ready to code!
