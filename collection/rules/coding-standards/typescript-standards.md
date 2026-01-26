---
name: TypeScript Coding Standards
tags:
  technology: [typescript, javascript, react, nextjs]
  feature: [frontend, backend, fullstack]
  priority: high
summary: Strict TypeScript guidelines for type-safe development
version: 1
---

# TypeScript Coding Standards

## Compiler Settings

Always use strict mode:
```json
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noUncheckedIndexedAccess": true
  }
}
```

## Type Definitions

### Prefer Interfaces for Objects
```typescript
// Good: Interface for object shapes
interface UserProfile {
  id: string;
  name: string;
  email: string;
  createdAt: Date;
}

// Good: Type for unions/intersections
type Status = 'active' | 'inactive' | 'pending';
type UserWithStatus = UserProfile & { status: Status };
```

### Never Use `any`
```typescript
// Bad
function processData(data: any): any {
  return data.value;
}

// Good: Use unknown and narrow
function processData(data: unknown): string {
  if (typeof data === 'object' && data !== null && 'value' in data) {
    return String(data.value);
  }
  throw new Error('Invalid data format');
}
```

### Explicit Return Types
```typescript
// Good: Explicit return type for public functions
async function fetchUser(id: string): Promise<User> {
  const response = await fetch(`/api/users/${id}`);
  return response.json();
}
```

## React Components

### Functional Components Only
```typescript
// Good: Functional component with typed props
interface ButtonProps {
  label: string;
  onClick: () => void;
  variant?: 'primary' | 'secondary';
  disabled?: boolean;
}

export function Button({
  label,
  onClick,
  variant = 'primary',
  disabled = false,
}: ButtonProps): JSX.Element {
  return (
    <button
      className={`btn btn-${variant}`}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
}
```

### Custom Hooks
```typescript
// Hooks must start with 'use'
function useUserData(userId: string): {
  user: User | null;
  loading: boolean;
  error: Error | null;
} {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    fetchUser(userId)
      .then(setUser)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [userId]);

  return { user, loading, error };
}
```

## Error Handling

```typescript
// Define custom error types
class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public code: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// Use Result pattern for operations that can fail
type Result<T, E = Error> =
  | { success: true; data: T }
  | { success: false; error: E };

async function safeApiCall<T>(
  fn: () => Promise<T>
): Promise<Result<T>> {
  try {
    const data = await fn();
    return { success: true, data };
  } catch (error) {
    return { success: false, error: error as Error };
  }
}
```
