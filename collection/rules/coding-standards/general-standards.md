---
name: General Coding Standards
tags:
  technology: [python, typescript, javascript, react]
  feature: [backend, frontend, fullstack]
  priority: high
summary: Universal coding standards covering simplicity, consistency, organization, and language-specific guidelines
version: 1
---

# General Coding Standards

## General Principles

### Simplicity
- Prefer simple solutions over clever ones
- Don't over-engineer - solve the current problem
- Three similar lines of code is better than a premature abstraction
- Only add complexity when clearly necessary

### Consistency
- Follow existing patterns in the codebase
- Match the style of surrounding code
- Use consistent naming conventions
- Don't mix paradigms unnecessarily

## Documentation & Naming

### Naming Conventions
- **Strict Lowercase**: All file and directory names must be lowercase
- **Separators**: Use hyphens (kebab-case) or underscores (snake_case) for multi-word names
- **Exceptions**: Specific system files if required by tools (e.g., `Dockerfile`, `Makefile`)

### Documentation Structure
- **Split by Topic**: Avoid monolithic files. Split into topic-specific documents
- **Task Linkage**: Technical tasks must clearly link to User Stories
- **Detail Level**: Tasks must specify frameworks, interfaces, and methods used
- **Best Practices**: Explicitly research and cite best practices before implementation

## Code Organization

### Files
- One module/class per file (generally)
- Group related functionality together
- Keep files under 500 lines when possible
- Use clear, descriptive file names

### Functions
- Single responsibility per function
- Keep functions under 50 lines when possible
- Clear input/output types
- Meaningful parameter names

### Comments
- Only add comments where logic isn't self-evident
- Don't add obvious comments ("increment counter")
- Document WHY, not WHAT
- Keep comments up to date with code changes

## Error Handling

### Patterns
- Handle errors at appropriate boundaries
- Don't swallow errors silently
- Provide actionable error messages
- Log with sufficient context for debugging

### Validation
- Validate at system boundaries (user input, external APIs)
- Trust internal code and framework guarantees
- Don't add redundant validation

## Testing

### Test Structure
- Arrange-Act-Assert pattern
- One assertion per test when possible
- Clear test names describing behavior
- Test edge cases and error conditions

### Coverage
- Focus on behavior, not line coverage
- Test public interfaces, not implementation details
- Integration tests for critical paths
- Don't test framework/library code

## Shell Scripts
- Use `set -e` for error handling
- Quote variables: `"$VAR"` not `$VAR`
- Check command existence before using
- Use shellcheck for validation
