---
name: Git Workflow Rules
tags:
  technology: [git]
  feature: [workflow, deployment]
  priority: high
summary: Git guardrails for safe version control operations
version: 1
---

# Git Workflow Rules

## Git Guardrails

### Never Do
- Force push to main/master
- Commit directly to protected branches
- Use --no-verify without approval
- Commit merge conflict markers

### Always Do
- Create descriptive commit messages
- Check git status before committing
- Stage only intended changes
- Pull before pushing

## Commit Message Format

Use conventional commits:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code change that neither fixes nor adds
- `test`: Adding tests
- `chore`: Maintenance tasks

### Examples

```bash
# Good
feat(auth): add JWT token refresh endpoint
fix(api): handle null response from external service
docs(readme): update installation instructions

# Bad
updated stuff
fix bug
WIP
```

## Git Worktree Guardrails

**For parallel worker execution using git worktrees.**

### Never Do
- Create worktrees for dependent tasks
- Modify the same file in multiple worktrees
- Leave orphaned worktrees after completion
- Merge worktrees with conflicts without resolution

### Always Do
- Use WorktreeManager context manager for auto-cleanup
- Verify tasks are independent before parallel execution
- Check worktree status before merging
- Handle cherry-pick failures gracefully

## Branch Naming

```
<type>/<ticket-id>-<short-description>
```

Examples:
- `feat/AUTH-123-jwt-refresh`
- `fix/API-456-null-handling`
- `chore/DEVOPS-789-update-ci`
