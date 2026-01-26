---
name: Python Coding Standards
tags:
  technology: [python, fastapi]
  feature: [backend, api]
  priority: high
summary: Coding standards and best practices for Python backend development
version: 1
---

# Python Coding Standards

## General Principles

### Style Guide
- Follow PEP 8 style guide
- Use type hints for all public interfaces
- Prefer f-strings over `.format()` or `%`
- Use `pathlib.Path` for file paths

### Naming Conventions
- `snake_case` for functions, variables, and modules
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Prefix private members with `_`

### Imports
```python
# Standard library imports
import os
from pathlib import Path

# Third-party imports
import fastapi
from pydantic import BaseModel

# Local imports
from .utils import helper
```

## Type Hints

Always use type hints for public functions:

```python
def process_data(
    items: list[dict[str, Any]],
    config: Optional[Config] = None,
) -> ProcessResult:
    """Process items with optional configuration."""
    ...
```

## Error Handling

```python
# Good: Specific exceptions with context
try:
    result = await database.query(sql)
except DatabaseConnectionError as e:
    logger.error(f"Database connection failed: {e}")
    raise ServiceUnavailable(f"Database unavailable: {e}")

# Bad: Bare except clauses
try:
    result = await database.query(sql)
except:  # Never do this!
    pass
```

## Async Best Practices

```python
# Use async for I/O operations
async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# Use asyncio.gather for parallel operations
results = await asyncio.gather(
    fetch_data(url1),
    fetch_data(url2),
    return_exceptions=True,
)
```

## Documentation

```python
def complex_function(
    data: dict[str, Any],
    options: ProcessOptions,
) -> ProcessResult:
    """
    Process data with the given options.

    Args:
        data: Input data dictionary with required keys: id, name, value
        options: Processing options including timeout and retry settings

    Returns:
        ProcessResult containing status and processed data

    Raises:
        ValidationError: If data is missing required keys
        TimeoutError: If processing exceeds options.timeout
    """
    ...
```
