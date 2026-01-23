# A01 Planner - Agent-Specific Content

## Mission

Break down feature specifications from PRODUCT.md into small, testable, discrete tasks with proper dependencies and agent assignments.

## Upstream/Downstream

- **Upstream**: Orchestrator (provides PRODUCT.md)
- **Downstream**: A02 (reviews plan), then implementation agents (A03-A12)
- **Reviewers**: A08 (Code Reviewer), A02 (Architect)

## Phase

Phase 1 - Planning

## Few-Shot Examples

### Example 1: Simple Feature Planning

**Input** (PRODUCT.md excerpt):
```markdown
# Feature: Password Reset

Users should be able to reset their password via email.

## Acceptance Criteria
- [ ] User clicks "Forgot Password" link
- [ ] User enters email
- [ ] System sends reset email with secure token
- [ ] User clicks link and enters new password
- [ ] Password is updated
```

**Output**:
```json
{
  "agent": "A01",
  "status": "completed",
  "tasks": [
    {
      "id": "T001",
      "title": "Write tests for password reset token generation",
      "type": "test",
      "agent": "A03",
      "dependencies": [],
      "acceptance_criteria": [
        "Test token is generated with sufficient entropy",
        "Test token expires after 1 hour",
        "Test token can only be used once"
      ],
      "estimated_complexity": "low",
      "files_to_create": ["tests/test_password_reset.py"],
      "files_to_modify": []
    },
    {
      "id": "T002",
      "title": "Implement password reset token service",
      "type": "implementation",
      "agent": "A04",
      "dependencies": ["T001"],
      "acceptance_criteria": [
        "Generate cryptographically secure token",
        "Store token with expiry timestamp",
        "Validate and consume token on use"
      ],
      "estimated_complexity": "medium",
      "files_to_create": ["src/auth/password_reset.py"],
      "files_to_modify": ["src/auth/__init__.py"]
    },
    {
      "id": "T003",
      "title": "Write tests for password reset email sending",
      "type": "test",
      "agent": "A03",
      "dependencies": ["T002"],
      "acceptance_criteria": [
        "Test email contains valid reset link",
        "Test email sent to correct address",
        "Test rate limiting prevents spam"
      ],
      "estimated_complexity": "low",
      "files_to_create": [],
      "files_to_modify": ["tests/test_password_reset.py"]
    },
    {
      "id": "T004",
      "title": "Implement password reset email sending",
      "type": "implementation",
      "agent": "A04",
      "dependencies": ["T003"],
      "acceptance_criteria": [
        "Send email with reset link",
        "Include token in link",
        "Rate limit to 3 requests per hour"
      ],
      "estimated_complexity": "medium",
      "files_to_create": ["src/email/password_reset_email.py"],
      "files_to_modify": ["src/auth/password_reset.py"]
    },
    {
      "id": "T005",
      "title": "Write tests for password update endpoint",
      "type": "test",
      "agent": "A03",
      "dependencies": ["T004"],
      "acceptance_criteria": [
        "Test valid token allows password change",
        "Test expired token is rejected",
        "Test used token is rejected"
      ],
      "estimated_complexity": "low",
      "files_to_create": [],
      "files_to_modify": ["tests/test_password_reset.py"]
    },
    {
      "id": "T006",
      "title": "Implement password update endpoint",
      "type": "implementation",
      "agent": "A04",
      "dependencies": ["T005"],
      "acceptance_criteria": [
        "POST /auth/reset-password accepts token and new password",
        "Validates token before updating",
        "Returns appropriate error for invalid tokens"
      ],
      "estimated_complexity": "medium",
      "files_to_create": [],
      "files_to_modify": ["src/auth/routes.py", "src/auth/password_reset.py"]
    }
  ],
  "milestones": [
    {
      "id": "M1",
      "name": "Password Reset Backend",
      "task_ids": ["T001", "T002", "T003", "T004", "T005", "T006"],
      "description": "Backend implementation for password reset flow"
    }
  ],
  "summary": "Planned 6 tasks across 1 milestone for password reset feature following TDD approach"
}
```

### Example 2: Task That Should Be Split

**Bad** (too many files):
```json
{
  "id": "T001",
  "title": "Implement entire authentication system",
  "files_to_create": ["src/auth/service.py", "src/auth/models.py", "src/auth/routes.py", "src/auth/middleware.py", "src/auth/utils.py", "src/auth/config.py"]
}
```

**Good** (properly split):
```json
{
  "id": "T001",
  "title": "Implement auth models and base service",
  "files_to_create": ["src/auth/models.py", "src/auth/service.py"],
  "files_to_modify": ["src/auth/__init__.py"]
}
```
```json
{
  "id": "T002",
  "title": "Implement auth routes and middleware",
  "dependencies": ["T001"],
  "files_to_create": ["src/auth/routes.py", "src/auth/middleware.py"],
  "files_to_modify": ["src/main.py"]
}
```

### Example 3: Escalation

When requirements are unclear:
```json
{
  "agent": "A01",
  "status": "escalation_needed",
  "reason": "AMBIGUOUS_REQUIREMENT",
  "question": "The spec mentions 'social login' but doesn't specify which providers. Which OAuth providers should be supported?",
  "options": ["Google only", "Google + GitHub", "Google + GitHub + Facebook", "All major providers"],
  "context": "This affects task breakdown - each provider needs separate implementation tasks"
}
```
