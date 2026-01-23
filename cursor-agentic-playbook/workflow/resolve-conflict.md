# Workflow Macro: Resolve Conflict (security vs architecture)

---

When reviewers disagree, resolve conservatively.

## Rules
- If **security** reviewer blocks (high/critical): treat as **blocked** until fixed.
- If architecture reviewer blocks: fix if it’s a major design flaw; otherwise document and proceed only with explicit acceptance.
- Prefer the more conservative decision when in doubt.

## Output
- What disagreed
- Final decision + rationale
- Concrete fix plan (or documented acceptance)
