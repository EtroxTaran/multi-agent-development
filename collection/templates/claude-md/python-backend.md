---
name: Python Backend Template
tags:
  technology: [python, fastapi]
  feature: [backend, api]
  priority: high
summary: CLAUDE.md template for Python/FastAPI backend projects
version: 1
---

# Python Backend Agent Context

You are working on a Python backend project using FastAPI.

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: SurrealDB (or specify)
- **Testing**: pytest, pytest-asyncio
- **Package Manager**: uv (preferred) or pip

## Coding Standards

### Style
- Follow PEP 8
- Use type hints for all public functions
- Use async/await for I/O operations
- Prefer f-strings over .format()

### Project Structure
```
src/
├── api/           # FastAPI routers
├── models/        # Pydantic models
├── services/      # Business logic
├── db/            # Database layer
└── utils/         # Helpers
tests/
├── unit/          # Unit tests
├── integration/   # Integration tests
└── conftest.py    # Fixtures
```

### Naming
- `snake_case` for functions, variables
- `PascalCase` for classes
- `UPPER_CASE` for constants

## Workflow Rules

1. **TDD Required**: Write failing tests first
2. **Type Hints**: All public functions must have type hints
3. **Documentation**: Add docstrings to public functions
4. **Error Handling**: Use specific exceptions, never bare `except:`

## Available Commands

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Type check
mypy src/

# Lint
ruff check src/

# Format
ruff format src/
```

## Security Guardrails

- Never commit secrets
- Always use parameterized queries
- Validate all external input with Pydantic
- Use HTTPS in production
