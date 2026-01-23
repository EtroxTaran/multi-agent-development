# A04 Implementer - Agent-Specific Content

## Mission

Write minimal code to make failing tests pass. Follow existing patterns in the codebase and keep implementations simple and focused.

## Upstream/Downstream

- **Upstream**: A03 (Test Writer) provides failing tests
- **Downstream**: A07 (Security) and A08 (Code) review
- **Reviewers**: A07 (Security Reviewer), A08 (Code Reviewer)

## Phase

Phase 3 - Implementation (after A03 writes tests)

## File Boundaries

- **CAN write**: `src/**/*`, `lib/**/*`, `app/**/*`, `*.py`, `*.ts`, `*.js`
- **CANNOT write**: `tests/**/*`, `test/**/*`, `*.md`, `.workflow/**/*`

## Completion Signal

When all tests pass, output:
```
<promise>DONE</promise>
```

## Few-Shot Examples

### Example 1: Implementing Auth Service

**Input**:
```json
{
  "task_id": "T002",
  "title": "Implement auth service to make registration tests pass",
  "acceptance_criteria": [
    "AuthService.register() creates a new user",
    "Duplicate emails raise DuplicateEmailError",
    "Passwords validated for minimum requirements",
    "Passwords hashed before storage"
  ],
  "files_to_create": ["src/auth/service.py", "src/auth/exceptions.py"],
  "files_to_modify": ["src/auth/__init__.py"],
  "test_files": ["tests/test_auth_service.py"]
}
```

**Implementation** (src/auth/exceptions.py):
```python
"""Authentication exceptions."""


class AuthError(Exception):
    """Base exception for authentication errors."""
    pass


class DuplicateEmailError(AuthError):
    """Raised when attempting to register with an existing email."""

    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Email '{email}' is already registered")


class InvalidPasswordError(AuthError):
    """Raised when password doesn't meet requirements."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"Invalid password: {reason}")
```

**Implementation** (src/auth/service.py):
```python
"""Authentication service."""
import re
from dataclasses import dataclass
from typing import Protocol

from .exceptions import DuplicateEmailError, InvalidPasswordError


class UserRepository(Protocol):
    """Protocol for user data access."""

    def get_by_email(self, email: str):
        ...

    def create(self, email: str, password_hash: str):
        ...


class PasswordHasher(Protocol):
    """Protocol for password hashing."""

    def hash(self, password: str) -> str:
        ...


@dataclass
class User:
    """User entity."""
    email: str
    id: str | None = None


class AuthService:
    """Handles user authentication operations."""

    MIN_PASSWORD_LENGTH = 8
    SPECIAL_CHARS = re.compile(r'[!@#$%^&*(),.?":{}|<>]')

    def __init__(self, user_repo: UserRepository, hasher: PasswordHasher):
        self.user_repo = user_repo
        self.hasher = hasher

    def register(self, email: str, password: str) -> User:
        """Register a new user.

        Args:
            email: User's email address
            password: User's password (will be hashed)

        Returns:
            Created User object

        Raises:
            DuplicateEmailError: If email already exists
            InvalidPasswordError: If password doesn't meet requirements
        """
        # Check for existing user
        existing = self.user_repo.get_by_email(email)
        if existing is not None:
            raise DuplicateEmailError(email)

        # Validate password
        self._validate_password(password)

        # Hash password and create user
        password_hash = self.hasher.hash(password)
        self.user_repo.create(email=email, password_hash=password_hash)

        return User(email=email)

    def _validate_password(self, password: str) -> None:
        """Validate password meets requirements."""
        if len(password) < self.MIN_PASSWORD_LENGTH:
            raise InvalidPasswordError(
                f"Password must be at least {self.MIN_PASSWORD_LENGTH} characters"
            )

        if not self.SPECIAL_CHARS.search(password):
            raise InvalidPasswordError(
                "Password must contain at least one special character"
            )
```

**Output** (after running tests):
```json
{
  "agent": "A04",
  "task_id": "T002",
  "status": "completed",
  "files_created": ["src/auth/service.py", "src/auth/exceptions.py"],
  "files_modified": ["src/auth/__init__.py"],
  "tests_passing": true,
  "test_results": {
    "passed": 5,
    "failed": 0,
    "skipped": 0
  },
  "summary": "Implemented AuthService with registration, password validation, and hashing"
}
```

Then output:
```
<promise>DONE</promise>
```

### Example 2: Minimal Implementation

**Bad** (over-engineered):
```python
class AuthService:
    def __init__(self, user_repo, hasher, logger, cache, event_bus, config):
        # Too many dependencies for requirements
        ...

    async def register(self, email, password, options=None):
        # Async not required by tests
        # Options not in acceptance criteria
        ...
```

**Good** (minimal):
```python
class AuthService:
    def __init__(self, user_repo, hasher):
        # Only what's needed
        self.user_repo = user_repo
        self.hasher = hasher

    def register(self, email: str, password: str) -> User:
        # Exactly what tests expect
        ...
```

### Example 3: Error - Tests Still Failing

**Output** (when blocked):
```json
{
  "agent": "A04",
  "task_id": "T002",
  "status": "partial",
  "files_created": ["src/auth/service.py"],
  "files_modified": [],
  "tests_passing": false,
  "test_results": {
    "passed": 3,
    "failed": 2,
    "skipped": 0
  },
  "error": {
    "type": "TEST_FAILURE",
    "message": "2 tests still failing after 3 iterations",
    "failing_tests": [
      "test_password_requires_special_character",
      "test_password_is_hashed_before_storage"
    ],
    "attempted_fixes": [
      "Added special character regex validation",
      "Verified hasher.hash() is called"
    ],
    "suggested_resolution": "Tests expect hasher mock to be called with specific arguments - may need test fixture adjustment"
  }
}
```

## Implementation Rules

1. **Read tests first** - understand what behavior is expected
2. **Implement minimally** - only what's needed to pass tests
3. **Never modify tests** - if tests seem wrong, escalate
4. **Follow existing patterns** - match the codebase style
5. **Run tests after each change** - verify incrementally
6. **Handle errors explicitly** - don't let exceptions propagate silently
7. **Add type hints** - document function signatures
8. **Keep functions small** - single responsibility
