# Feature Name: Smoke Test – Hello Endpoint

## Summary
Build a minimal HTTP service with a single `GET /health` endpoint that returns JSON `{ "status": "ok" }`.

## Problem Statement
We need a tiny, deterministic feature to validate that the Cursor global workflow can: plan tasks, write tests first, implement minimal code, and verify.

## Acceptance Criteria
- [ ] `GET /health` returns HTTP 200
- [ ] Response JSON is exactly `{ "status": "ok" }`
- [ ] At least one automated test asserts the response body and status code
- [ ] Verification step reports the test command used and its pass/fail summary

## Example Inputs/Outputs

### Example 1
Request:
```http
GET /health
```

Response:
```json
{ "status": "ok" }
```

### Example 2
Request:
```http
GET /health
```

Response status:
```text
200
```

## Technical Constraints
- Must be simple and dependency-light
- No authentication
- No database

## Testing Strategy
- Unit or integration test that calls the route handler or an in-memory server

## Definition of Done
- [ ] Implementation exists
- [ ] Tests exist and pass
- [ ] No hardcoded secrets
- [ ] Clear instructions on how to run tests
- [ ] Verified by the verifier workflow
