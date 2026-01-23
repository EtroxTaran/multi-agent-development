# /orchestrate

Run the full product→plan→validate→implement→verify workflow. Delegate to subagents.

## Inputs
- Product mission + acceptance criteria (prefer `Docs/PRODUCT.md` or `docs/`)
- Any architecture/tech docs
- Preferred test commands (if not obvious)

## Steps
1. Discover docs and summarize requirements.
2. Use `/planner` to create the task plan.
3. Validate in parallel with `/validator-security` + `/validator-architecture`.
4. Implement tasks via TDD (`/test-writer` → `/implementer`).
5. Verify with `/verifier` and report evidence.
6. Run independent tasks in parallel when safe (e.g., docs update + test writing).
