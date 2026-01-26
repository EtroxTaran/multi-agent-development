---
name: Core Rules
tags:
  technology: [python, typescript, javascript]
  feature: [workflow]
  priority: critical
summary: Essential rules that apply to ALL agents and tasks
version: 1
---

# Core Rules

## Never Do

1. **Commit secrets** - API keys, credentials, or passwords
2. **Use eval/exec** - With user input (Remote Code Execution)
3. **SQL concatenation** - Use parameterized queries instead
4. **Trust user input** - Always validate and sanitize
5. **Leave debug code** - console.log, print statements
6. **Commit commented code** - Delete unused code
7. **Skip tests** - Never mark complete with failing tests
8. **Ignore linter errors** - Fix before committing

## Always Do

1. **Validate input** - At system boundaries
2. **Use parameterized queries** - For database access
3. **Run tests** - Before marking complete
4. **Follow patterns** - Match existing code style
5. **Clean up** - Remove temporary files
6. **Error handling** - No empty catch blocks
