# Workflow Macro: Discover (docs intake)

Use this prompt in Cursor Chat when starting a fresh project or feature.

---

Discover and read project documentation first.

## Doc locations (search in order)
1. `Docs/**/*.md`
2. `docs/**/*.md`
3. root `PRODUCT.md` / `README.md`

## Output
- A concise summary:
  - what we’re building
  - why (problem statement)
  - acceptance criteria
  - constraints (security, performance, compatibility)
- A list of missing info as 1–3 targeted questions (only if necessary).
