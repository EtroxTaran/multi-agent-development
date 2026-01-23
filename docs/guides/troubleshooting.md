## 16. Troubleshooting

### 16.1 Common Issues

#### Issue: "PRODUCT.md validation failed"
**Cause**: PRODUCT.md doesn't meet minimum requirements

**Solution**: Ensure PRODUCT.md has:
- Feature Name (5-100 chars)
- Summary (50-500 chars)
- Problem Statement (min 100 chars)
- At least 3 acceptance criteria with `- [ ]` items
- At least 2 Example Inputs/Outputs with code blocks
- No placeholders like `[TODO]`, `[TBD]`

#### Issue: "OrchestratorBoundaryError"
**Cause**: Orchestrator tried to write outside allowed paths

**Solution**: The orchestrator can only write to `.workflow/` and `.project-config.json`. If code changes are needed, they must go through worker agents.

#### Issue: "WorktreeError: not a git repository"
**Cause**: Parallel workers require git

**Solution**: Initialize a git repository or run without `--parallel`:
```bash
cd projects/my-app && git init
```

#### Issue: "Agent failed on both primary and backup CLI"
**Cause**: Both Claude and fallback CLI failed

**Solution**:
1. Check escalation file for detailed error
2. Verify CLI tools are working: `./scripts/init.sh check`
3. Check rate limits haven't been exceeded

#### Issue: "Max iterations exceeded"
**Cause**: Task couldn't be completed in allowed retries

**Solution**:
1. Check escalation for specific failure reason
2. Review the feedback from reviewers
3. Consider breaking task into smaller subtasks

### 16.2 Debugging Commands

```bash
# View human-readable logs
tail -f projects/<name>/.workflow/coordination.log

# View machine-parseable logs
cat projects/<name>/.workflow/coordination.jsonl | jq

# Check escalations
cat projects/<name>/.workflow/escalations/*.json | jq

# Resume after fixing issues
python -m orchestrator --project <name> --resume

# Reset and retry
python -m orchestrator --project <name> --reset
python -m orchestrator --project <name> --start
```

---
