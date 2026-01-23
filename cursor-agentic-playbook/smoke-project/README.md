# Smoke Project (for validating your Cursor global workflow)

This is a tiny dependency-free project you can open in Cursor to validate:
- docs-first planning
- TDD loop
- verification gate
- subagent auto-delegation

## What to do in Cursor

1. Open this folder in Cursor:
   - `cursor-agentic-playbook/smoke-project/`
2. Ensure Global Rules are set (copy/paste once):
   - `../global-rules-for-ai.md`
3. Ensure subagents are installed (copy once to `~/.cursor/agents/`):
   - `../subagents/*.md`
4. Start the workflow:
   - Use `../workflow/orchestrate.md` as your prompt

## Local verification (outside Cursor)

From this directory:

```bash
python -m unittest discover -s tests -p "test_*.py"
```
