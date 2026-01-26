---
name: TDD Workflow
tags:
  technology: [python, typescript, javascript]
  feature: [testing, workflow]
  priority: high
summary: Test-Driven Development workflow for quality code
version: 1
---

# TDD Workflow

## Core Principle

**Write failing tests FIRST, then implement code to make them pass.**

## The TDD Cycle

```
┌─────────────────────────────────────────────┐
│                                              │
│   1. RED    →   2. GREEN   →   3. REFACTOR  │
│   (Write    →   (Make      →   (Clean up    │
│    failing      tests          while tests  │
│    test)        pass)          stay green)  │
│                                              │
└─────────────────────────────────────────────┘
```

## Step-by-Step Process

### 1. RED: Write a Failing Test

```python
# tests/test_calculator.py
def test_add_positive_numbers():
    calc = Calculator()
    result = calc.add(2, 3)
    assert result == 5
```

Run the test - it should FAIL:
```bash
pytest tests/test_calculator.py -v
# FAILED - Calculator not defined
```

### 2. GREEN: Write Minimal Code

Write the simplest code that makes the test pass:

```python
# src/calculator.py
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
```

Run the test - it should PASS:
```bash
pytest tests/test_calculator.py -v
# PASSED
```

### 3. REFACTOR: Clean Up

Now refactor while keeping tests green:
- Remove duplication
- Improve naming
- Add type hints
- Optimize if needed

## Rules

1. **Never write production code without a failing test**
2. **Write only enough code to make the test pass**
3. **One test at a time**
4. **Keep tests fast** (< 100ms per test)
5. **Tests must be independent** (no shared state)

## Test Structure: Arrange-Act-Assert

```python
def test_user_creation():
    # Arrange: Set up test data
    user_data = {"name": "Alice", "email": "alice@example.com"}

    # Act: Perform the action
    user = create_user(user_data)

    # Assert: Verify the result
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
    assert user.id is not None
```

## What to Test

| Test | Don't Test |
|------|------------|
| Your business logic | Framework/library code |
| Edge cases | Getters/setters |
| Error handling | External APIs (mock them) |
| Integration points | Implementation details |

## Completion Criteria

- [ ] All acceptance criteria have corresponding tests
- [ ] All tests pass
- [ ] No skipped tests
- [ ] Test coverage meets threshold (80%+)
