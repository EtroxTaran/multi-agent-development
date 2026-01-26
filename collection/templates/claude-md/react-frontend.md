---
name: React Frontend Template
tags:
  technology: [typescript, react, nextjs]
  feature: [frontend, ui]
  priority: high
summary: CLAUDE.md template for React/Next.js frontend projects
version: 1
---

# React Frontend Agent Context

You are working on a React frontend project.

## Tech Stack

- **Language**: TypeScript (strict mode)
- **Framework**: React 18+ / Next.js 14+
- **Styling**: Tailwind CSS / CSS Modules
- **State**: React Query for server state, Zustand for client state
- **Testing**: Vitest + React Testing Library + Playwright

## Coding Standards

### TypeScript
- `strict: true` always
- Never use `any` - use `unknown` and narrow
- Explicit return types for all functions
- Prefer `interface` for object shapes

### React
- Functional components only
- Custom hooks must start with `use`
- Keep state local, lift only when necessary
- Use memo/useMemo/useCallback only for measured perf issues

### Project Structure
```
src/
├── app/           # Next.js app router pages
├── components/    # Reusable components
│   ├── ui/        # Base UI components
│   └── features/  # Feature-specific components
├── hooks/         # Custom hooks
├── lib/           # Utilities, API clients
├── types/         # Type definitions
└── styles/        # Global styles
```

## Workflow Rules

1. **Component First**: Design component interface before implementation
2. **Test Critical Paths**: E2E tests for user journeys
3. **Accessibility**: All interactive elements must be keyboard accessible
4. **Performance**: Lighthouse score > 90 for all pages

## Available Commands

```bash
# Development
npm run dev

# Type check
npm run typecheck

# Lint
npm run lint

# Test
npm test

# E2E tests
npm run test:e2e

# Build
npm run build
```

## Security Guardrails

- Never use dangerouslySetInnerHTML without DOMPurify
- Validate all form inputs
- Use HTTPS for all API calls
- Implement CSRF protection for mutations
