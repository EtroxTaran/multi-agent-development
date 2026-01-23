# Completion Signaling

## CLI-Specific Patterns

Your CLI is **{{PRIMARY_CLI}}**. Use the appropriate completion signal:

### Claude CLI
When done, output:
```
<promise>DONE</promise>
```

### Cursor CLI
When done, output JSON with status:
```json
{"status": "done"}
```

### Gemini CLI
When done, output one of:
```
DONE
```
or
```
COMPLETE
```

## Important

- **ONLY** signal completion when ALL acceptance criteria are met
- If you cannot complete the task, do NOT signal completion
- Instead, output an error with details (see Error Handling section)

## Partial Progress

If you made progress but hit a blocker:
1. Save your work (commit files modified so far)
2. Output an error explaining what's blocking
3. Do NOT signal completion
