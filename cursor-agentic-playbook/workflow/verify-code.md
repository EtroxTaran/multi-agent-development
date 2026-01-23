# Workflow Macro: Verify (hard gate)

---

Run the `/verifier` subagent as a hard completion gate.

## Verifier should:
- restate what is claimed “done”
- run the smallest strong set of checks (tests/typecheck/lint/build as appropriate)
- look for common edge cases and missing error handling

## Output
- Verified evidence (commands + pass/fail summary)
- Missing/incomplete items
- Next actions to reach approval
