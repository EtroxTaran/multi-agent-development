# QA Engineer Guide

**Audience**: Quality Assurance Engineers, SDETs.

In the Conductor ecosystem, QA is not an "afterthought". It is the **Source of Truth**.
This guide explains how to verify the AI's work and how to leverage the system for automated regression testing.

---

## 🧪 The "Test First" Philosophy

Conductor enforces **Hard TDD** (Test Driven Development).

1.  **Constraint**: The System *cannot* write implementation code until a test fails.
2.  **Implication for QA**: You don't just "test the app". You **audit the tests**.

### Reviewing Agent-Written Tests
When `A03 (Test Writer)` submits a test plan, your job is to check:
*   **Coverage**: Do the tests cover all Acceptance Criteria in `PRODUCT.md`?
*   **Mocking**: Are the agents mocking too much? (e.g., Mocking the database instead of using the test DB).
*   **Edge Cases**: Did the agent test for `null`, `undefined`, or negative numbers?

---

## 🔍 How to Run Verification

You don't need to manually click around the UI. Conductor provides CLI tools for QA.

### 1. Run the Full Suite
To run every test (Unit + Integration + E2E) across the project:
```bash
./scripts/run-tests.sh --all
```
*   **Red**: Failure. The build stops.
*   **Green**: Success. The agents accept the task.

### 2. Targeting Specific Features
If the agents just finished the `Auth` module, run only those tests:
```bash
pytest tests/auth/ --verbose
```

### 3. The Verification Dashboard
On the **Dashboard** `http://localhost:3000`, navigate to the **Tasks** tab.
Click on any **Completed** task to see:
*   **Test File**: `tests/test_auth.py`
*   **Test Output**: `5 passed, 0 failed`
*   **Coverage Report**: `98%` coverage of `src/auth.py`.

---

## 🐞 Handling Bugs

When you find a bug that the agents missed:

### Do NOT Fix the Code.
If you fix the code manually, the agents might overwrite it next time they run.

### DO Fix the Test.
1.  Open the relevant test file (e.g., `tests/test_login.py`).
2.  Add a **New Failing Test Case** that reproduces your bug.
    ```python
    def test_bug_repro_123():
        assert login("admin", "") == False # Agents missed empty password check
    ```
3.  Commit this test.
4.  Run the **Fixer Agent**:
    ```bash
    ./scripts/init.sh run my-project --fix
    ```
5.  Watch as `A05 (Bug Fixer)` sees the failure and patches the code to make your test pass.

---

## 🤖 Automating E2E Tests

For UI/Frontend work, Conductor uses **Playwright**.
The `A10 (Integration Tester)` agent writes these.

To run them headlessly:
```bash
npx playwright test
```
To run them with UI (to watch the bot click):
```bash
npx playwright test --ui
```
