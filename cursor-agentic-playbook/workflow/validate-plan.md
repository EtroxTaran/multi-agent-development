# Workflow Macro: Validate Plan (security + architecture)

---

Validate the plan before implementation.

Run these in parallel:
- `/validator-security` to review the plan for OWASP/security risks (blocking: high/critical).
- `/validator-architecture` to review the plan for architecture/scalability risks.

Then produce a consolidated decision:
- approved / needs_changes / rejected
- list of blocking issues (if any)
- concrete plan edits to address issues
