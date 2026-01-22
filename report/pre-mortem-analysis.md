# Pre-Mortem Analysis: Meta-Architect
Date: 2026-01-21

This is a full pre-mortem analysis of the Meta-Architect system. The intent is to enumerate what is going wrong or could go wrong across the entire system, with emphasis on high-impact, likely failure modes. This is intentionally exhaustive and blunt.

## Scope and Inputs
- Source code reviewed across orchestrator, LangGraph workflow, validators, utils, integrations, agents, and scripts.
- Project docs reviewed: `README.md`, `docs/quick-start.md`, `docs/SPECIALIST-AGENTS-DESIGN.md`, `docs/COMPREHENSIVE-SYSTEM-ANALYSIS.md`.
- This is a static analysis of code and docs; no runtime execution performed.

## Executive Summary (Highest-Risk Failures)
These are the most dangerous failure modes based on impact and likelihood.

1. **State persistence is fragile in async LangGraph flows**: fallback to in-memory checkpointer risks loss of state, broken resumability, and inconsistent recovery after crashes, especially during long multi-agent runs.
2. **Task loop can deadlock or spin**: dependency cycles, missing dependencies, or poor task selection heuristics can halt progress or loop indefinitely without meaningful escalation.
3. **Agent output parsing and JSON expectations are brittle**: non-JSON responses, partial JSON, or model drift can break planning/validation/implementation pipelines.
4. **Security scanner and coverage checks are too shallow**: regex-only scanning and coverage parsing can miss real vulnerabilities or give false confidence, letting unsafe code pass.
5. **Boundary enforcement is bypassable through symlinks or path tricks**: high-stakes writes can escape intended boundaries in edge cases.
6. **Parallel worktree merges can corrupt state**: cherry-pick conflicts, partial merges, or stale worktrees can reintroduce defects or lose changes.
7. **Workflow relies on external CLIs and networked services**: outages, rate limits, and version drift can stall the pipeline without robust fallback.
8. **Documentation drift undermines safe usage**: README and scripts are inconsistent with actual repo state, leading to incorrect usage and broken workflows.
9. **Escalation flow is a single choke-point**: if human escalation fails or is ignored, the system cannot self-recover safely.
10. **Cost and time runaway**: iterative Ralph loop + retries can spiral, exhausting budgets or rate limits without safe cutoffs.

## Critical Failure Scenarios (Pre-Mortem)
These are realistic stories of how the system fails in production use.

1. **Crash mid-workflow loses state**: SQLite checkpointer is not used in async context; run falls back to memory. A crash or terminal disconnect loses all state, requiring manual reconstruction and risking inconsistent partial writes to `.workflow/`.
2. **Stuck task loop**: Tasks with unsatisfied dependencies are never selected; router loops `select_task` without progress until retries are exhausted. Human escalation gets triggered but no clear resolution path is present.
3. **Agent output drift**: Claude/Cursor/Gemini outputs JSON with extra commentary. Parsing fails, causing planning/validation nodes to mark results as errors and retry until max retries are exhausted.
4. **False security pass**: Regex scanner misses SSRF, auth logic flaws, deserialization bugs, or dependency vulnerabilities. Security scan passes; unsafe code ships.
5. **Boundary bypass**: A symlink in a project points from a safe path into `src/` or `tests/`. Boundary validation resolves paths, but edge cases or missing checks allow writes outside intended directories.
6. **Worktree merge conflicts**: Parallel worktrees modify overlapping files. Cherry-pick partially applies, leaving conflict markers or missing changes. Workflow proceeds without verifying merge integrity.
7. **Toolchain mismatch**: Environment checker mis-detects project type or uses wrong test/build command, resulting in false "green" or false failures that block progress.
8. **Cost runaway**: Ralph loop + retries + parallel workers lead to hundreds of LLM calls. Rate limiter blocks, but workflow logic keeps retrying, stalling for hours and burning budget.
9. **Documentation mismatch**: Users follow README commands referencing removed scripts; init or run fails, and no remediation is shown in CLI. Users abandon or misconfigure the system.
10. **Log and trace bloat**: High-volume logs grow faster than cleanup; log rotation errors or permission issues fill disk and crash the orchestrator.

## Risk Register (High-Level)
Severity: Critical | High | Medium | Low. Likelihood: High | Medium | Low.

| ID | Area | Failure Mode | Severity | Likelihood | Impact |
|---|---|---|---|---|---|
| R1 | State | Checkpointer fallback to memory, state loss | Critical | Medium | Cannot resume; corrupted workflow progress |
| R2 | Task loop | Dependency deadlock / infinite loop | High | Medium | Workflow stalls, human escalation needed |
| R3 | Agent IO | Non-JSON outputs break pipeline | High | High | Planning/validation/implementation fail |
| R4 | Security | Regex scanner misses real vulns | Critical | High | Unsafe code passes security gate |
| R5 | Boundaries | Symlink/path bypass | Critical | Medium | Orchestrator writes code or secrets |
| R6 | Worktrees | Merge conflicts / partial cherry-picks | High | Medium | Code integrity loss |
| R7 | Env check | Wrong test/build commands | High | Medium | False pass or false failure |
| R8 | Rate limits | Cost/time runaway | High | Medium | Stalled workflow, budget burn |
| R9 | Docs | Instruction drift | Medium | High | Users fail to run workflow |
| R10 | Escalation | No reliable human loop | High | Medium | Workflow dead-ends |
| R11 | Logging | Disk fill / rotation failure | Medium | Medium | Process crash |
| R12 | Approval | Conflicting reviews unresolved | Medium | Medium | Rework or halt |

## Detailed Findings by Subsystem

### 1) LangGraph Workflow and Routing
What can go wrong:
- **Parallel fan-in merges can lose data**: Reducers merge lists and dicts; if fields overlap or partial updates occur, newer data can overwrite earlier agent feedback.
- **Router logic assumes specific `next_decision` values**: unexpected outputs can route to the wrong phase or skip required checks.
- **Retries are coarse**: repeated failures of planning or validation can loop without improving inputs, wasting cost.
- **Legacy `implementation_node` vs. task loop**: two implementation paths exist; mismatched usage risks running the wrong flow or skipping task-based logic.

Why it matters:
- The workflow is the primary safety system; routing mistakes compromise correctness and safety guarantees.

Likely triggers:
- New node output fields, differing JSON shapes, or changes in agent prompts.

### 2) State Persistence and Recovery
What can go wrong:
- **Checkpointing not resilient in async**: LangGraph may fall back to memory, losing state on crash.
- **State file corruption**: partial writes or concurrent writes can corrupt `state.json` despite backup logic.
- **State adapter divergence**: LangGraph state and legacy state manager can drift in shape or timing.

Why it matters:
- State drives resumption, task selection, and human escalation. Corruption leads to incorrect decisions.

### 3) Task Breakdown and Selection
What can go wrong:
- **Dependency cycles and deadlocks**: heuristic dependency inference can create cycles, leaving no available tasks.
- **Task granularity mismatch**: tasks too large make iteration slow; tasks too small lead to overhead and context fragmentation.
- **Priority heuristics are speculative**: a high-priority task may require unfinished prerequisites but still be selected.

Why it matters:
- The task loop is the engine for incremental delivery; if it breaks, the whole system stops.

### 4) Agent Invocation and Output Parsing
What can go wrong:
- **Non-JSON responses**: model changes, tool failures, or prompt injection can cause invalid JSON that fails parsing.
- **Timeouts and truncated outputs**: long tasks exceed timeouts; partial outputs get parsed as failures.
- **Prompt injection via project files**: product docs or code comments can influence agent instructions.

Why it matters:
- Every phase depends on agent output integrity; parse failures cascade to retries or aborts.

### 5) TDD Enforcement and Ralph Loop
What can go wrong:
- **False RED/GREEN detection**: parsing test output can misclassify failures as passes or vice versa.
- **Flaky tests create endless loop**: Ralph loop retries while tests flake, never stabilizing.
- **Coverage of acceptance criteria is heuristic**: it can claim coverage without real behavioral validation.

Why it matters:
- TDD is a core safety promise; if enforcement is weak, quality regressions slip through.

### 6) Validators (Product, Environment, Coverage, Security)
What can go wrong:
- **ProductValidator false positives/negatives**: strict format rules reject valid specs; weak rules allow bad specs.
- **EnvironmentChecker mis-detection**: project type inferred incorrectly; wrong test/build commands are used.
- **CoverageChecker parsing gaps**: non-standard coverage formats or paths cause incorrect thresholds.
- **SecurityScanner is regex-only**: blind to logic bugs, dependency vulns, authorization flaws, and many OWASP classes.

Why it matters:
- Validators are the gates. If they are wrong, the workflow gives false confidence or blocks good work.

### 7) Boundary Enforcement
What can go wrong:
- **Symlink bypass**: safe-looking path resolves to forbidden target; if normalization is incomplete, boundary checks can be bypassed.
- **Pattern gaps**: new directories or file types might not be covered by forbidden patterns.
- **Worker vs orchestrator boundary confusion**: outer orchestrator may accidentally touch inner project files.

Why it matters:
- Violating boundaries breaks the safety model and can cause unreviewed code changes.

### 8) Git Worktrees and Parallel Execution
What can go wrong:
- **Non-git external projects**: worktree operations fail hard; parallel workers abort.
- **Cherry-pick conflicts**: conflicting edits cause partial merges; no automated conflict resolution.
- **Stale worktrees**: leftover worktrees can lead to confusing status and unintended merges.

Why it matters:
- Parallel execution is a high-risk feature; failure can corrupt code and state.

### 9) Logging, Observability, and Audit
What can go wrong:
- **Log volume explosion**: high-frequency logs or JSON traces exceed disk space.
- **Redaction misses**: secrets might leak into logs if patterns miss new keys or formats.
- **Trace data bloat**: tracing every tool call can become enormous, slowing the system.

Why it matters:
- Logging is used for recovery and compliance; if it fails, diagnosis becomes impossible.

### 10) Human-in-the-Loop and Approval Gates
What can go wrong:
- **Escalation output incomplete**: human cannot decide because context is missing or inconsistent.
- **Approval deadlock**: approval gate expects human response but no interface exists to provide it.
- **Policy mismatch**: approval thresholds or policies are too strict, causing unnecessary rework.

Why it matters:
- Human escalation is the ultimate safety valve; if it fails, the system halts.

### 11) Integrations (Linear, Markdown Tracker, MCP)
What can go wrong:
- **MCP unavailability**: calls to Linear via MCP fail; tasks are partially created or out of sync.
- **Local tracker corruption**: SHA tracking fails or file permissions prevent updates.
- **External API changes**: Linear API changes break workflows without immediate detection.

Why it matters:
- Integrations are optional but can destabilize if not isolated properly.

### 12) UI and Display
What can go wrong:
- **Concurrency on UI state**: multiple threads update UI state without consistent locking; display glitches or errors.
- **Rich dependency mismatch**: running in non-Rich environments can crash or degrade to unreadable output.

Why it matters:
- UI is how operators understand progress; broken UI hides failures.

### 13) Documentation and Operator Experience
What can go wrong:
- **README and scripts drift**: onboarding fails or uses wrong commands.
- **Too many entry points**: scripts, CLI, and docs conflict; operators pick wrong flow.
- **Incomplete error messages**: failures do not explain how to fix prerequisites or configuration.

Why it matters:
- Operational usability is directly tied to adoption and reliability.

## Cross-Cutting Security Risks
- **Prompt injection**: product docs or code could trick agents into bypassing safety instructions.
- **Shell command injection**: any place that interpolates command strings is sensitive.
- **Secrets exposure**: logs, traces, and error outputs may contain tokens or keys.
- **Boundary violations**: any unvalidated write is a potential code or secrets overwrite.
- **Supply chain blind spots**: no dependency scanning for known CVEs.

## Cross-Cutting Reliability Risks
- **Retry storms**: multiple nodes retry in parallel, causing exponential cost/time.
- **Clock/time drift**: time-based decisions in logs or state can become inconsistent.
- **Partial failures**: one agent fails but others succeed, causing inconsistent merged state.

## Failure Matrix by Workflow Phase
This is how failure propagates through each phase.

1. **Prerequisites**: missing CLIs, missing `PRODUCT.md`, wrong env. Failure: workflow aborts before helpful guidance.
2. **Product validation**: overly strict validator blocks, or too lenient validator allows weak specs.
3. **Planning**: JSON parse failure, hallucinated plan, inconsistent tasks.
4. **Validation**: non-JSON output or conflicting reviews; fan-in merge loses issues.
5. **Approval gate**: no human response, workflow hangs.
6. **Pre-implementation**: wrong project type or test/build commands.
7. **Task breakdown**: malformed tasks, dependency cycles.
8. **Implement task**: TDD loop fails due to flaky tests or bad prompts.
9. **Verify task**: mismatched test path or incorrect file validation; tasks marked incomplete.
10. **Build verification**: false failure or false pass due to incorrect command.
11. **Verification (reviews)**: model output mismatch; approval policy rejects.
12. **Coverage check**: parsing errors or missing report.
13. **Security scan**: regex misses critical vulnerability.
14. **Completion**: summary incorrect due to incomplete state; missing commit data.

## Gaps in Current Defense Layers
- **No dependency vulnerability scanning** (e.g., SCA). Only regex source scanning.
- **No deterministic schema validation for all agent outputs**: inconsistent parsing and error handling.
- **No strong idempotency** across retries; partial progress may be duplicated or overwritten.
- **No centralized cancellation**: user abort does not propagate cleanly through all nodes.
- **No single source of truth for docs**: multiple instruction sets drift.

## Suggested Hardening (Prioritized)
These are not implementation tasks, just risk mitigations.

1. **Make persistent checkpointing mandatory** in LangGraph runs and fail fast if it cannot initialize.
2. **Schema-validate all agent outputs** with strict JSON schema and automatic repair steps.
3. **Add dependency scanning** (SCA) to security phase; treat as blocking if critical.
4. **Harden boundary validation** against symlinks and path traversal in all write operations.
5. **Add deadlock detection and resolution** in task selection with explicit cycle reporting.
6. **Centralize retry and budget limits** to prevent runaway loops.
7. **Standardize build/test commands** per project type with explicit overrides.
8. **Create a single authoritative operator guide** and deprecate outdated README flows.
9. **Add deterministic merge validation** after worktree cherry-picks (e.g., `git diff --check`).
10. **Improve escalation UX** with clear instructions and required fields for human input.

## Residual Risk (Even After Fixes)
- LLM outputs remain probabilistic; strict schema checks will reduce but not eliminate failures.
- Dependency and environment drift are ongoing risks in long-running workflows.
- Parallel worktree execution remains high-risk due to merge complexity.

## Bottom Line
The system is ambitious and well-structured, but it is not yet resilient against the most common failure modes: state loss, agent output drift, shallow security validation, and workflow deadlocks. If you run it on real projects without tightening these areas, you should expect stalled workflows, false approvals, and occasional unsafe code changes.
