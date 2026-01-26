---
name: Code Quality Guardrails
tags:
  technology: [python, typescript, javascript]
  feature: [testing, workflow]
  priority: high
summary: Code quality guardrails to prevent common issues
version: 1
---

# Code Quality Guardrails

## Never Do

### Debug Code
- Leave debug statements (console.log, print, debugger)
- Commit commented-out code
- Create empty catch blocks
- Use magic numbers without constants

### Type Safety
- Use `any` type in TypeScript (use `unknown` instead)
- Suppress linter rules without valid reason and comment
- Ignore linter/type errors

## Always Do

### Before Committing
- Run tests before marking complete
- Check for regressions in existing tests
- Follow existing code patterns
- Clean up temporary files
- Fix all linter errors before committing

### TypeScript Specific
- Ensure `npm run typecheck` leads to 0 errors
- Use strict mode (`"strict": true` in tsconfig)
- Explicit return types for public functions

### Python Specific
- Run `ruff check` and `mypy` before committing
- Use type hints for public interfaces
- Follow PEP 8 style guide

## Code Review Checklist

Before marking code as complete:

- [ ] All tests pass
- [ ] No new linter warnings
- [ ] Type checking passes
- [ ] No debug statements
- [ ] No commented-out code
- [ ] Constants used instead of magic numbers
- [ ] Error handling is complete (no empty catch blocks)
- [ ] Follows existing code patterns

## Complexity Guidelines

| Metric | Threshold | Action if Exceeded |
|--------|-----------|-------------------|
| Function length | 50 lines | Split into smaller functions |
| File length | 500 lines | Extract modules |
| Cyclomatic complexity | 10 | Simplify logic |
| Parameters | 5 | Use object parameter |
