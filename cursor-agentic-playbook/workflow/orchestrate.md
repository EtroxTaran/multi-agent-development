# Workflow Macro: Orchestrate (product→plan→validate→implement→verify)

Use this prompt in Cursor Chat.

---

Use the `/orchestrator` subagent to run a full workflow for this project.

## Inputs
- Product mission + acceptance criteria (prefer `Docs/PRODUCT.md` or `docs/`; otherwise I will paste them here).
- Any architecture/tech docs (ADRs, diagrams, API contracts).
- Preferred stack/testing commands (if not obvious).

## Workflow
1. Discover docs and summarize what we’re building.
2. Delegate to `/planner` to produce a task plan (tasks, file scope, tests, deps).
3. Delegate to `/validator-security` and `/validator-architecture` in parallel to review the plan.
4. Implement tasks iteratively using TDD:
   - `/test-writer` writes failing tests first
   - `/implementer` implements minimal code to pass
5. Run `/verifier` as a hard gate. Do not claim completion without verification evidence.
6. If there are independent tasks, run them in parallel subagents.

## Research
If Perplexity MCP is available, use it to confirm up-to-date best practices relevant to the stack and feature.
