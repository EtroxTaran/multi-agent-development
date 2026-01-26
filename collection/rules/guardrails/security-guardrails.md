---
name: Security Guardrails
tags:
  technology: [python, typescript, javascript]
  feature: [security, auth, api, database]
  priority: critical
summary: Critical security guardrails to prevent common vulnerabilities
version: 1
---

# Security Guardrails

## NEVER Do These

### 1. Commit Secrets
```python
# NEVER hardcode secrets
API_KEY = "sk-1234567890abcdef"  # WRONG!

# Always use environment variables
API_KEY = os.environ.get("API_KEY")
```

### 2. Use eval() or exec() with User Input
```python
# NEVER do this
result = eval(user_input)  # Remote Code Execution!

# Safe alternative: Use specific parsers
import json
result = json.loads(user_input)
```

### 3. SQL String Concatenation
```python
# NEVER build SQL with string concatenation
query = f"SELECT * FROM users WHERE id = '{user_id}'"  # SQL Injection!

# Always use parameterized queries
query = "SELECT * FROM users WHERE id = $id"
result = await db.query(query, {"id": user_id})
```

### 4. Trust User Input
```python
# NEVER trust user input directly
filename = request.query_params["file"]
with open(f"/data/{filename}") as f:  # Path Traversal!
    return f.read()

# Always validate and sanitize
from pathlib import Path
filename = Path(request.query_params["file"]).name
safe_path = Path("/data") / filename
if not safe_path.resolve().is_relative_to(Path("/data").resolve()):
    raise HTTPException(403, "Invalid path")
```

## ALWAYS Do These

### 1. Validate All External Input
```python
from pydantic import BaseModel, EmailStr, constr

class UserCreate(BaseModel):
    email: EmailStr
    username: constr(min_length=3, max_length=50, pattern=r'^[a-zA-Z0-9_]+$')
    password: constr(min_length=8)
```

### 2. Use Secure Defaults
```python
# Secure cookie settings
response.set_cookie(
    key="session",
    value=token,
    httponly=True,
    secure=True,
    samesite="lax",
)
```

### 3. Escape Output to Prevent XSS
```typescript
// React automatically escapes, but be careful with dangerouslySetInnerHTML
// NEVER do this without sanitization:
<div dangerouslySetInnerHTML={{ __html: userContent }} />

// Use a sanitizer if you must render HTML
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userContent) }} />
```

### 4. Apply Least Privilege
```python
# Database user should only have necessary permissions
# Don't run as root/admin
# Limit file system access
```

## OWASP Top 10 Checklist

- [ ] A01: Broken Access Control - Enforce authorization on every endpoint
- [ ] A02: Cryptographic Failures - Use strong encryption, never roll your own
- [ ] A03: Injection - Always parameterize queries, validate input
- [ ] A04: Insecure Design - Threat model before implementation
- [ ] A05: Security Misconfiguration - Disable debug mode in production
- [ ] A06: Vulnerable Components - Keep dependencies updated
- [ ] A07: Authentication Failures - Use proven auth libraries
- [ ] A08: Data Integrity Failures - Sign all sensitive data
- [ ] A09: Logging Failures - Log security events, never log secrets
- [ ] A10: SSRF - Validate and restrict outbound requests
