# CLI Examples (Extended)

<!-- SHARED: Detailed CLI examples for reference -->
<!-- Version: 1.0 -->
<!-- Last Updated: 2026-01-27 -->

This file contains detailed CLI examples. For quick reference, see `cli-reference.md`.

---

## Claude Code CLI Examples

### Full Example (Enhanced)
```bash
# Complex multi-file task with all features
claude -p "Implement user authentication" \
    --output-format json \
    --permission-mode plan \
    --max-budget-usd 2.00 \
    --fallback-model sonnet \
    --json-schema schemas/tasks-schema.json \
    --allowedTools "Read,Write,Edit,Bash(npm*),Bash(pytest*)" \
    --max-turns 50

# Ralph loop iteration with session continuity
claude -p "Fix failing tests" \
    --output-format json \
    --resume T1-abc123def456 \
    --max-budget-usd 0.50 \
    --allowedTools "Read,Write,Edit,Bash(pytest*)" \
    --max-turns 15
```

### Basic Example
```bash
claude -p "Analyze this code" \
    --output-format json \
    --allowedTools "Read,Grep,Glob" \
    --max-turns 5
```

---

## Cursor Agent CLI Examples

### Full Example
```bash
cursor-agent --print \
    --output-format json \
    --force \
    "Review this code for security issues"
```

### Common Mistakes
- `cursor-agent -p "prompt"` - Wrong! `-p` means `--print`, not prompt
- Prompt must be LAST argument

---

## Gemini CLI Examples

### Full Example
```bash
gemini --model gemini-2.0-flash \
    --yolo \
    "Review architecture of this system"
```

### Common Mistakes
- `gemini --output-format json` - Wrong! Flag doesn't exist
- `gemini -p "prompt"` - Wrong! No `-p` flag

---

## Python Orchestrator Modules

These modules are available for autonomous decision-making.

### Session Manager
```python
from orchestrator.agents import SessionManager

manager = SessionManager(project_dir)
args = manager.get_resume_args("T1")  # Returns ["--resume", "session-id"] or []
session = manager.create_session("T1")
manager.close_session("T1")
```

### Error Context Manager
```python
from orchestrator.agents import ErrorContextManager

manager = ErrorContextManager(project_dir)
context = manager.record_error(task_id="T1", error_message="...", attempt=1, stderr=stderr_output)
retry_prompt = manager.build_retry_prompt("T1", original_prompt)
manager.clear_task_errors("T1")
```

### Budget Manager
```python
from orchestrator.agents import BudgetManager

manager = BudgetManager(project_dir)
if manager.can_spend("T1", 0.50):
    pass  # Proceed
manager.record_spend("T1", "claude", actual_cost)
budget = manager.get_invocation_budget("T1")
```

### Audit Trail
```python
from orchestrator.audit import get_project_audit_trail

trail = get_project_audit_trail(project_dir)
with trail.record("claude", "T1", prompt) as entry:
    result = run_command(...)
    entry.set_result(success=True, exit_code=0, cost_usd=0.05)
```

### ClaudeAgent (Enhanced)
```python
from orchestrator.agents import ClaudeAgent

agent = ClaudeAgent(project_dir, enable_session_continuity=True, default_fallback_model="sonnet")
result = agent.run_task(task)  # Auto-detects plan mode
result = agent.run(prompt, task_id="T1", use_plan_mode=True, budget_usd=2.00)
```

---

## Complete Workflow Examples

### Example 1: New Nested Project
```bash
./scripts/init.sh init my-api
# Add: projects/my-api/Documents/, PRODUCT.md, CLAUDE.md
./scripts/init.sh run my-api
```

### Example 2: External Project
```bash
./scripts/init.sh run --path ~/repos/existing-project
# Or: python -m orchestrator --project-path ~/repos/existing-project --use-langgraph --start
```

### Example 3: Parallel Implementation
```bash
./scripts/init.sh run my-app --parallel 3
```

### Example 4: Check and Resume
```bash
./scripts/init.sh status my-app
python -m orchestrator --project my-app --resume
```
