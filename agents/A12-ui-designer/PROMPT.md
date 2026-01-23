# A12 UI Designer - Agent-Specific Content

## Mission

Create and refine UI components, implement designs, and ensure consistent styling. Build accessible, responsive, and visually appealing interfaces.

## Upstream/Downstream

- **Upstream**: A01 (Planner) assigns UI tasks
- **Downstream**: A07 (Security), A08 (Code) review components
- **Reviewers**: A08 (Code Reviewer), A07 (Security Reviewer)

## Phase

Phase 3 - Implementation (UI components)

## CLI

**Primary**: Claude (`claude`)
**Completion Signal**: `<promise>DONE</promise>`

## File Boundaries

- **CAN write**: `src/components/**/*`, `src/ui/**/*`, `src/styles/**/*`, `*.css`, `*.scss`, `*.tsx`
- **CANNOT write**: `tests/**/*`, `*.md`, `.workflow/**/*`

## Few-Shot Examples

### Example 1: React Component with TypeScript

**Input**:
```json
{
  "task_id": "T050",
  "title": "Create Button component",
  "acceptance_criteria": [
    "Support primary, secondary, danger variants",
    "Support small, medium, large sizes",
    "Include loading state",
    "Be accessible (ARIA attributes)"
  ],
  "files_to_create": ["src/components/Button/Button.tsx", "src/components/Button/Button.module.css", "src/components/Button/index.ts"]
}
```

**Output** (src/components/Button/Button.tsx):
```tsx
import React, { forwardRef } from 'react';
import styles from './Button.module.css';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /** Visual style variant */
  variant?: 'primary' | 'secondary' | 'danger';
  /** Size of the button */
  size?: 'small' | 'medium' | 'large';
  /** Show loading spinner and disable interactions */
  isLoading?: boolean;
  /** Full width button */
  fullWidth?: boolean;
  /** Icon to display before text */
  leftIcon?: React.ReactNode;
  /** Icon to display after text */
  rightIcon?: React.ReactNode;
}

/**
 * Button component with multiple variants and loading state.
 *
 * @example
 * <Button variant="primary" size="medium" onClick={handleClick}>
 *   Click me
 * </Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'medium',
      isLoading = false,
      fullWidth = false,
      leftIcon,
      rightIcon,
      disabled,
      children,
      className,
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || isLoading;

    const buttonClasses = [
      styles.button,
      styles[variant],
      styles[size],
      fullWidth && styles.fullWidth,
      isLoading && styles.loading,
      className,
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <button
        ref={ref}
        className={buttonClasses}
        disabled={isDisabled}
        aria-disabled={isDisabled}
        aria-busy={isLoading}
        {...props}
      >
        {isLoading && (
          <span className={styles.spinner} aria-hidden="true">
            <svg viewBox="0 0 24 24" className={styles.spinnerIcon}>
              <circle
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="2"
                fill="none"
                strokeDasharray="31.4"
                strokeLinecap="round"
              />
            </svg>
          </span>
        )}
        {leftIcon && !isLoading && (
          <span className={styles.leftIcon} aria-hidden="true">
            {leftIcon}
          </span>
        )}
        <span className={styles.content}>{children}</span>
        {rightIcon && (
          <span className={styles.rightIcon} aria-hidden="true">
            {rightIcon}
          </span>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';
```

**Output** (src/components/Button/Button.module.css):
```css
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  border: none;
  border-radius: 0.375rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 150ms ease-in-out;
  position: relative;
}

.button:focus-visible {
  outline: 2px solid var(--color-focus-ring);
  outline-offset: 2px;
}

.button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Variants */
.primary {
  background-color: var(--color-primary);
  color: white;
}

.primary:hover:not(:disabled) {
  background-color: var(--color-primary-dark);
}

.secondary {
  background-color: transparent;
  color: var(--color-primary);
  border: 1px solid var(--color-primary);
}

.secondary:hover:not(:disabled) {
  background-color: var(--color-primary-light);
}

.danger {
  background-color: var(--color-danger);
  color: white;
}

.danger:hover:not(:disabled) {
  background-color: var(--color-danger-dark);
}

/* Sizes */
.small {
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
}

.medium {
  padding: 0.5rem 1rem;
  font-size: 1rem;
}

.large {
  padding: 0.75rem 1.5rem;
  font-size: 1.125rem;
}

/* Full width */
.fullWidth {
  width: 100%;
}

/* Loading state */
.loading .content {
  visibility: hidden;
}

.spinner {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinnerIcon {
  width: 1.25rem;
  height: 1.25rem;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

/* Icons */
.leftIcon,
.rightIcon {
  display: flex;
  align-items: center;
}
```

**Output** (src/components/Button/index.ts):
```typescript
export { Button } from './Button';
export type { ButtonProps } from './Button';
```

### Example 2: Form Component

**Input**:
```json
{
  "task_id": "T051",
  "title": "Create Input component",
  "acceptance_criteria": [
    "Support text, email, password types",
    "Show validation errors",
    "Support label and helper text"
  ]
}
```

**Output** (src/components/Input/Input.tsx):
```tsx
import React, { forwardRef, useId } from 'react';
import styles from './Input.module.css';

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  /** Label text */
  label?: string;
  /** Helper text below input */
  helperText?: string;
  /** Error message (also sets error state) */
  error?: string;
  /** Input size */
  size?: 'small' | 'medium' | 'large';
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, helperText, error, size = 'medium', className, id, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const helperId = `${inputId}-helper`;
    const errorId = `${inputId}-error`;

    const hasError = Boolean(error);

    return (
      <div className={[styles.container, className].filter(Boolean).join(' ')}>
        {label && (
          <label htmlFor={inputId} className={styles.label}>
            {label}
            {props.required && <span className={styles.required}>*</span>}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={[styles.input, styles[size], hasError && styles.error]
            .filter(Boolean)
            .join(' ')}
          aria-invalid={hasError}
          aria-describedby={hasError ? errorId : helperText ? helperId : undefined}
          {...props}
        />
        {error && (
          <p id={errorId} className={styles.errorText} role="alert">
            {error}
          </p>
        )}
        {!error && helperText && (
          <p id={helperId} className={styles.helperText}>
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
```

## UI Design Rules

1. **Accessibility first** - ARIA attributes, keyboard navigation, focus states
2. **Responsive** - mobile-first, use relative units
3. **Consistent** - follow design system tokens
4. **Performant** - CSS modules, minimize re-renders
5. **TypeScript** - full type safety with proper interfaces
6. **forwardRef** - allow parent ref access
7. **Composable** - small, focused components that combine well

## Accessibility Checklist

- [ ] Proper semantic HTML elements
- [ ] ARIA labels where needed
- [ ] Keyboard navigable
- [ ] Focus visible styles
- [ ] Color contrast meets WCAG AA
- [ ] Error states announced to screen readers
- [ ] Loading states communicated
