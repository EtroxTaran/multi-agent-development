# Cursor Global Rules for AI (Agentic Web Dev Baseline)

Paste this into **Cursor Settings → Rules for AI**.

These rules are **repo-agnostic**: they do not assume Conductor/SurrealDB state files exist.

## Operating principles

- **Be correct over fast**: if unsure, ask for missing info or inspect the code/docs.
- **Scope discipline**: do the smallest change that satisfies the requirement.
- **No hidden work**: don’t claim done without running the relevant checks.

## Documentation-first workflow (product → plan → build → verify)

- Prefer to work from **project documentation** when available:
  - `Docs/PRODUCT.md` (preferred) or `docs/product.md` / `PRODUCT.md` (fallback)
  - Any supporting docs under `Docs/**` or `docs/**`
- Before implementing, produce a short **task plan** with:
  - tasks with acceptance criteria
  - files to create/modify per task
  - tests to add/run per task
  - dependencies between tasks
- If docs are missing: ask the user to provide a product mission + acceptance criteria, or create a minimal `Docs/PRODUCT.md` skeleton.

## Subagents and parallelization

- Prefer subagents for specialized work (planning, validation, verification, UI testing).
- Run independent subagents in parallel when safe (e.g., security + architecture validation).
- If auto-delegation doesn’t trigger, explicitly call the subagent by name (e.g., `/planner`, `/verifier`).

## TDD and quality gates (required)

- **TDD default**: write failing tests first, then implement, then refactor.
- **Verification gate**: do not mark a task complete unless:
  - relevant tests were executed (or an explicit reason why they can’t be)
  - failures were addressed
- Prefer these checks when applicable:
  - backend: unit/integration tests + lint + typecheck
  - frontend: unit tests + typecheck + lint + basic runtime sanity (build/dev)

## Security guardrails (required)

- Never introduce secrets into the repo (keys, tokens, credentials, `.env` contents).
- Never use `eval()` / `exec()` / dynamic code execution with user-controlled input.
- Never build SQL queries via string concatenation; use parameterized queries.
- Validate and sanitize external inputs at boundaries (HTTP, CLI args, webhooks).
- Avoid logging sensitive data (tokens, passwords, PII).
- Prefer secure defaults (HTTPS, secure cookies, least privilege).

## Safe editing + git hygiene

- **Read before edit**: inspect current code before changing it.
- Avoid unrelated refactors during feature work.
- Don’t delete files without an explicit request.
- Don’t bypass safety checks:
  - no `--no-verify`
  - no force push
  - don’t amend pushed commits

## TypeScript / React defaults (when applicable)

- TypeScript strictness: avoid `any`; prefer `unknown` + narrowing.
- Prefer small, composable components; keep state local unless lifting is justified.
- Accessibility is non-optional for UI: keyboard navigation + aria where needed.

## Output expectations

- When asked for structured outputs (plans, reviews), return **concise JSON** or a clearly structured checklist.
- Include **test plan** and **verification evidence** (commands run + pass/fail summary).
