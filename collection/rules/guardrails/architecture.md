---
name: Architecture Guardrails
tags:
  technology: [python, typescript, javascript]
  feature: [architecture, design]
  priority: high
summary: Architecture and design pattern guardrails for Gemini reviews
version: 1
---

# Architecture Guardrails

## Anti-Patterns to Flag

1. **God classes** - Classes that do everything
2. **Tight coupling** - Components that can't change independently
3. **Circular dependencies** - A depends on B depends on A
4. **Leaky abstractions** - Implementation details exposed
5. **Over-engineering** - Unnecessary complexity for the problem
6. **Magic numbers** - Use named constants

## Design Principles to Verify

### SOLID
- **S**ingle Responsibility - One reason to change per class
- **O**pen/Closed - Open for extension, closed for modification
- **L**iskov Substitution - Subtypes must be substitutable
- **I**nterface Segregation - Small, focused interfaces
- **D**ependency Inversion - Depend on abstractions

### Modularity
- High cohesion within modules
- Low coupling between modules
- Clear layer boundaries
- Separation of concerns

## Scalability Checklist

- [ ] Can this scale horizontally?
- [ ] Are there obvious bottlenecks?
- [ ] Is state management appropriate?
- [ ] Are database queries efficient (no N+1)?
- [ ] Are async operations used where appropriate?
