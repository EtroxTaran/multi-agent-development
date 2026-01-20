---
description: Add a lesson learned to shared rules
allowed-tools: ["Read", "Edit", "Bash"]
---

# Add Lesson Learned

Record a bug fix, mistake, or pattern learned so all agents remember it.

## Instructions

1. Ask the user for lesson details:
   - What was the issue?
   - What was the root cause?
   - How was it fixed?
   - What agents does it apply to? (all, claude, cursor, gemini)

2. Add entry to `shared-rules/lessons-learned.md`:
   - Add at the TOP of the "Recent Lessons" section
   - Use today's date
   - Follow the template format

3. Run the sync script:
   ```bash
   python scripts/sync-rules.py
   ```

4. Confirm the lesson was propagated to all agent files.

## Template

```markdown
### YYYY-MM-DD - Brief Title

- **Issue**: What went wrong or was discovered
- **Root Cause**: Why it happened
- **Fix**: How it was fixed
- **Prevention**: Rule or check to prevent recurrence
- **Applies To**: all | claude | cursor | gemini
- **Files Changed**: List of affected files (if applicable)
```

## Example Usage

User: "We learned that the gemini CLI doesn't support --output-format"

Add to lessons-learned.md:
```markdown
### 2026-01-20 - Gemini CLI No Output Format

- **Issue**: Gemini CLI calls were failing
- **Root Cause**: Used --output-format flag which doesn't exist
- **Fix**: Removed flag, wrap output in JSON externally
- **Prevention**: Check CLI --help before using new flags
- **Applies To**: all
```
