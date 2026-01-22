# Orchestrate Skill

Multi-agent workflow orchestration using native Claude Code features.

## Usage

```
/orchestrate [--autonomous] [--project <name>]
```

### Arguments
- `--autonomous`: Run fully autonomously without asking for approval (default: interactive)
- `--project <name>`: Use nested project in `projects/<name>/` (default: current directory)

## Execution Modes

### Interactive Mode (Default)
- **Asks for approval** before starting implementation
- **Pauses on errors** and asks how to proceed
- **Shows progress** and asks clarifying questions
- Best for: New projects, complex features, learning the codebase

### Autonomous Mode (`--autonomous`)
- **Makes all decisions** automatically based on best practices
- **Retries up to 3 times** on failure before aborting
- **Never asks questions** - proceeds with best-guess decisions
- Best for: Well-defined projects, overnight runs, CI/CD integration

## Architecture

```
Claude Code (This Session = Orchestrator)
    |
    +-- Task Tool --> Worker Claude (70% cheaper than subprocess)
    |
    +-- Bash Tool --> cursor-agent CLI (security review)
    |
    +-- Bash Tool --> gemini CLI (architecture review)
    |
    +-- Read/Write --> .workflow/state.json (state persistence)
```

## Workflow Phases

| Phase | Name | Agents | Method |
|-------|------|--------|--------|
| 0 | Discussion | Claude | Direct conversation (skipped in autonomous) |
| 1 | Planning | Claude Worker | Task tool |
| 2 | Validation | Cursor + Gemini | Bash (parallel, optional) |
| 3 | Implementation | Claude Workers | Task tool (per task) |
| 4 | Verification | Cursor + Gemini | Bash (parallel, optional) |
| 5 | Completion | Claude | Direct |

## State Management

State is persisted in `.workflow/state.json`:

```json
{
  "project_name": "my-project",
  "project_dir": "/path/to/project",
  "current_phase": 2,
  "execution_mode": "hitl",
  "phase_status": {
    "discussion": "completed",
    "planning": "completed",
    "validation": "in_progress",
    "implementation": "pending",
    "verification": "pending",
    "completion": "pending"
  },
  "plan": { ... },
  "tasks": [ ... ],
  "current_task_id": null,
  "validation_feedback": {
    "cursor": { ... },
    "gemini": { ... }
  },
  "verification_feedback": {
    "cursor": { ... },
    "gemini": { ... }
  },
  "errors": [],
  "updated_at": "2026-01-22T12:00:00Z"
}
```

## Project Directory Resolution

The skill determines the project directory as follows:

1. **Current directory mode** (default): Works in the current working directory
   ```
   /orchestrate                    # Uses current directory
   ```

2. **Nested project mode**: Works in `projects/<name>/`
   ```
   /orchestrate --project my-app   # Uses projects/my-app/
   ```

## Execution Instructions

### Starting a Workflow

1. **Determine project directory**:
   - If `--project <name>`: Use `projects/<name>/`
   - Otherwise: Use current working directory

2. **Discover and read documentation** (Phase 0.5):
   - See "Phase 0.5: Document Discovery" section below
   - This MUST happen before planning

3. **Parse arguments**:
   - Check for `--autonomous` flag
   - Set `execution_mode`: "afk" if autonomous, "hitl" otherwise

4. **Initialize state** (if new):
   ```json
   {
     "project_name": "<dirname>",
     "project_dir": "<absolute path>",
     "execution_mode": "hitl|afk",
     "current_phase": 0,
     "phase_status": {
       "discovery": "pending",
       "discussion": "pending",
       "planning": "pending",
       "validation": "pending",
       "implementation": "pending",
       "verification": "pending",
       "completion": "pending"
     },
     "docs_index": null
   }
   ```

5. **Execute phases sequentially** using appropriate skills/tools.

### Phase 0.5: Document Discovery

**CRITICAL**: Before planning, read ALL documentation from the Docs/ folder to build full context.

#### Step 1: Find Documentation Folder

Search for documentation in this order (use first found):
1. `Docs/` - Primary documentation folder (preferred)
2. `Documents/` - Legacy naming (fallback)
3. `docs/` - Lowercase alternative (fallback)

```
Glob: Docs/**/*.md
```

If no folder found, check fallback locations. If all missing, apply "Missing Docs/ Behavior" below.

#### Step 2: Read All Markdown Files

Recursively read all `.md` files in the documentation folder:

**Priority Order:**
1. `Docs/PRODUCT.md` - Primary feature specification (REQUIRED)
2. `Docs/vision/*.md` - Product vision and goals
3. `Docs/architecture/*.md` - Technical constraints and design
4. `Docs/requirements/*.md` - Functional and non-functional requirements
5. `Docs/decisions/*.md` - Architecture decision records (ADRs)
6. Any other `.md` files in `Docs/`

Use Glob to find files:
```
Glob: Docs/**/*.md
```

Then read each file with the Read tool.

#### Step 3: Build Context Summary

After reading all documentation, build a mental model of:
- **What we're building** (from vision docs)
- **Why** (from problem statement in PRODUCT.md)
- **How it should work** (from architecture docs)
- **Constraints** (from requirements docs)
- **Past decisions** (from ADRs)
- **Success criteria** (from acceptance criteria in PRODUCT.md)

#### Step 4: Save Documentation Index

Save an index of discovered documentation to `.workflow/docs-index.json`:

```json
{
  "discovered_at": "2026-01-22T12:00:00Z",
  "docs_folder": "Docs/",
  "files": [
    {
      "path": "Docs/PRODUCT.md",
      "type": "specification",
      "summary": "Feature specification for user authentication"
    },
    {
      "path": "Docs/vision/product-vision.md",
      "type": "vision",
      "summary": "High-level product goals and target users"
    },
    {
      "path": "Docs/architecture/overview.md",
      "type": "architecture",
      "summary": "System architecture and component design"
    }
  ],
  "total_files": 5,
  "has_product_md": true
}
```

Update state with `docs_index` reference.

#### Missing Docs/ Behavior

**Interactive Mode (hitl)**:
If Docs/ folder is missing or empty:
1. Inform user: "No Docs/ folder found in project root."
2. Use AskUserQuestion tool with options:
   - **Create template**: Create a Docs/ folder with template files
   - **Specify location**: Point to where your documentation is
   - **Continue anyway**: Proceed without documentation (not recommended)
3. Wait for user response before proceeding

**Autonomous Mode (afk)**:
If Docs/ folder is missing or empty:
1. Log error: "Docs/ folder required for autonomous mode. Cannot proceed without documentation."
2. Set `phase_status.discovery = "failed"`
3. **ABORT workflow** - do NOT proceed without documentation
4. Exit with clear error message explaining what's needed

#### Fallback: PRODUCT.md in Root

If no Docs/ folder exists but `PRODUCT.md` exists in project root:
1. Log warning: "Using legacy PRODUCT.md location. Consider moving to Docs/PRODUCT.md"
2. Read root `PRODUCT.md` as the specification
3. Proceed with limited context (no supporting documentation)
4. In autonomous mode: Still abort - autonomous requires full Docs/ folder

### Phase 0: Discussion

**Interactive Mode**: Gather requirements through conversation:
- Ask about preferences, constraints, priorities
- Document decisions in `CONTEXT.md`
- Update state: `phase_status.discussion = "completed"`

**Autonomous Mode**: Skip this phase entirely - proceed directly to planning based on PRODUCT.md.

### Phase 1: Planning

Use Task tool to spawn a planning worker:

```
Task(
  subagent_type="Plan",
  prompt="""
  Create an implementation plan for the feature specified in the project documentation.

  ## Documentation to Read

  Read ALL documentation discovered in Phase 0.5:

  **Required:**
  - Docs/PRODUCT.md (feature specification)

  **If they exist (check .workflow/docs-index.json):**
  - Docs/vision/*.md (product vision, goals)
  - Docs/architecture/*.md (technical constraints, design patterns)
  - Docs/requirements/*.md (functional/non-functional requirements)
  - Docs/decisions/*.md (architecture decision records)
  - CONTEXT.md (developer preferences from discussion)

  ## Context Summary

  Before planning, verify you understand:
  - What we're building (from vision docs)
  - Why (from problem statement)
  - Technical constraints (from architecture docs)
  - Success criteria (from acceptance criteria)

  ## Output: plan.json

  Create plan.json with:
  - Feature overview (from PRODUCT.md)
  - Architecture notes (from Docs/architecture/)
  - Tasks breakdown (small, focused tasks)
  - File changes per task
  - Test strategy per task
  - Dependencies between tasks

  Each task should:
  - Touch max 3 files to create
  - Touch max 5 files to modify
  - Have clear acceptance criteria
  - Be completable in <10 minutes
  - Respect architecture constraints from Docs/architecture/
  """,
  run_in_background=false
)
```

Save result to `.workflow/phases/planning/plan.json`.

**Interactive Mode**: Show plan summary to user and ask for approval before proceeding.

**Autonomous Mode**: Proceed directly to validation without asking.

Update state: `phase_status.planning = "completed"`, `current_phase = 2`.

### Phase 2: Validation

**Optional**: Skip if Cursor/Gemini CLIs are not available.

Run Cursor and Gemini in parallel via Bash (if available):

**Cursor (Security Focus)**:
```bash
cursor-agent --print --output-format json "
Review .workflow/phases/planning/plan.json for:
- Security vulnerabilities in proposed changes
- Code quality concerns
- Testing coverage adequacy
- OWASP Top 10 risks

Return JSON:
{
  \"agent\": \"cursor\",
  \"approved\": true|false,
  \"score\": 1-10,
  \"assessment\": \"summary\",
  \"concerns\": [{\"area\": \"\", \"severity\": \"high|medium|low\", \"description\": \"\"}],
  \"blocking_issues\": []
}
" > .workflow/phases/validation/cursor-feedback.json
```

**Gemini (Architecture Focus)**:
```bash
gemini --yolo "
Review .workflow/phases/planning/plan.json for:
- Architecture patterns and design
- Scalability considerations
- Technical debt risks
- Maintainability

Return JSON:
{
  \"agent\": \"gemini\",
  \"approved\": true|false,
  \"score\": 1-10,
  \"assessment\": \"summary\",
  \"concerns\": [{\"area\": \"\", \"severity\": \"high|medium|low\", \"description\": \"\"}],
  \"blocking_issues\": []
}
" > .workflow/phases/validation/gemini-feedback.json
```

**Approval Criteria (Phase 2)**:
- Combined score >= 6.0
- No blocking issues from either agent
- If conflict: Security (Cursor) weight 0.8, Architecture (Gemini) weight 0.7

**Interactive Mode**: If validation fails, show issues and ask user how to proceed:
- [Retry] - Modify plan and re-validate
- [Skip] - Proceed to implementation anyway
- [Abort] - Stop workflow

**Autonomous Mode**: If validation fails, retry up to 3 times. After max retries, skip validation and proceed with a warning.

Update state: `validation_feedback`, `phase_status.validation = "completed"`, `current_phase = 3`.

### Phase 3: Implementation

For each task in plan.tasks:

1. **Select next task** (respecting dependencies)
2. **Spawn worker Claude** via Task tool:

```
Task(
  subagent_type="general-purpose",
  prompt="""
  ## Task: {task.title}

  ## User Story
  {task.user_story}

  ## Acceptance Criteria
  {task.acceptance_criteria}

  ## Files to Create
  {task.files_to_create}

  ## Files to Modify
  {task.files_to_modify}

  ## Test Files
  {task.test_files}

  ## Instructions
  1. Read CLAUDE.md for coding standards (if exists)
  2. Write failing tests FIRST (TDD)
  3. Implement code to make tests pass
  4. Run tests to verify: pytest or npm test
  5. Signal completion with: TASK_COMPLETE

  ## Constraints
  - Only modify files listed above
  - Follow existing code patterns
  - No security vulnerabilities
  """,
  run_in_background=false
)
```

3. **Update task status** in state
4. **Handle errors**:
   - **Interactive Mode**: Ask user how to proceed (Retry/Skip/Abort)
   - **Autonomous Mode**: Retry up to 3 times, then mark task as failed and continue
5. **Repeat** until all tasks complete

Update state: `phase_status.implementation = "completed"`, `current_phase = 4`.

### Phase 4: Verification

**Optional**: Skip if Cursor/Gemini CLIs are not available.

Run Cursor and Gemini in parallel via Bash (if available):

**Cursor (Code Review)**:
```bash
cursor-agent --print --output-format json "
Review the implemented code for:
- Security vulnerabilities (OWASP Top 10)
- Code quality and best practices
- Test coverage adequacy
- Potential bugs

Check files changed in implementation.

Return JSON:
{
  \"agent\": \"cursor\",
  \"approved\": true|false,
  \"score\": 1-10,
  \"assessment\": \"summary\",
  \"issues\": [{\"file\": \"\", \"line\": 0, \"severity\": \"\", \"description\": \"\"}],
  \"blocking_issues\": []
}
" > .workflow/phases/verification/cursor-review.json
```

**Gemini (Architecture Review)**:
```bash
gemini --yolo "
Review the implemented code for:
- Architecture compliance with plan
- Design pattern correctness
- Scalability concerns
- Technical debt introduced

Return JSON:
{
  \"agent\": \"gemini\",
  \"approved\": true|false,
  \"score\": 1-10,
  \"assessment\": \"summary\",
  \"issues\": [{\"file\": \"\", \"concern\": \"\", \"severity\": \"\"}],
  \"blocking_issues\": []
}
" > .workflow/phases/verification/gemini-review.json
```

**Approval Criteria (Phase 4)**:
- BOTH agents must approve
- Score >= 7.0 from each
- No blocking issues

**Interactive Mode**: If not approved, show issues and ask user:
- [Fix Issues] - Return to Phase 3 to fix
- [Accept Anyway] - Proceed with warnings
- [Abort] - Stop workflow

**Autonomous Mode**: If not approved, retry fixes up to 3 times. After max retries, complete with warnings logged.

Update state: `verification_feedback`, `phase_status.verification = "completed"`, `current_phase = 5`.

### Phase 5: Completion

Generate summary documentation:

1. Create `.workflow/phases/completion/summary.json`:
   - Features implemented
   - Files changed
   - Tests added
   - Review scores

2. Create UAT document if configured

3. Generate handoff brief for session resume

Update state: `phase_status.completion = "completed"`.

## Error Handling

### Interactive Mode (hitl)

**On Phase Failure**:
1. Log error to state.errors
2. Show error details to user
3. Ask: [Retry] / [Skip] / [Abort]
4. Wait for user decision

**On Agent Timeout**:
1. Inform user of timeout
2. Ask: [Retry] / [Skip Agent] / [Abort]

**On Conflict**:
1. Show conflicting feedback from agents
2. Ask user to make final decision

### Autonomous Mode (afk)

**On Phase Failure**:
1. Log error to state.errors
2. Increment retry count (max 3)
3. If max retries: Skip phase with warning OR abort if critical
4. Continue to next phase

**On Agent Timeout**:
1. Log timeout to state
2. Skip agent and note in summary
3. Continue without that agent's review

**On Conflict**:
Use automatic resolution:
- Security issues: Cursor weight 0.8
- Architecture issues: Gemini weight 0.7
- If still tied: Prefer the more conservative option

## Resuming Workflows

1. Read `.workflow/state.json`
2. Check `current_phase` and `phase_status`
3. Resume from last incomplete phase
4. Preserve all previous feedback and decisions

## Token Efficiency

| Component | Old (Subprocess) | New (Native) | Savings |
|-----------|------------------|--------------|---------|
| Worker Claude spawn | ~13k tokens | ~4k tokens | 70% |
| Context passing | Full duplication | Filtered | 60% |
| State management | External DB | Native files | Simpler |

## Related Skills

- `/plan-feature` - Detailed planning phase
- `/validate-plan` - Detailed validation phase
- `/implement-task` - Single task implementation
- `/verify-code` - Detailed verification phase
- `/resolve-conflict` - Conflict resolution
- `/call-cursor` - Cursor agent wrapper
- `/call-gemini` - Gemini agent wrapper
