# Quality Assurance Protocols

Conductor is designed with a "trust but verify" mindset. We assume LLMs will make mistakes, and we build systems to catch them.

---

## 👀 The 4-Eyes Protocol

**Rule**: No code is merged unless it has been successfully verified by **two distinct AI models** with **opposing goals**.

### The Reviewers
1.  **Cursor (Security Lens)**:
    *   Goal: "Find reasons to reject this (Safety)."
    *   Looks for: Data leaks, uncontrolled inputs, weak auth.
2.  **Gemini (Architecture Lens)**:
    *   Goal: "Find reasons to reject this (Quality)."
    *   Looks for: Spaghetti code, lack of comments, bad naming.

### The Mechanism
After Implementation (Phase 3) finishes, both agents run in parallel.
*   If **Both Approve**: The feature moves to Completion.
*   If **One Rejects**: We enter **Conflict Resolution**.
*   If **Both Reject**: The feature is sent back to Implementation with the feedback.

---

## ⚔️ Conflict Resolution

What happens when Gemini says "Code is great!" but Cursor says "It's insecure!"?

We use a **Weighted Voting System**.

```python
WEIGHTS = {
    "security_critical": {
        "cursor": 0.9,  # Cursor opinion matters most for security
        "gemini": 0.1
    },
    "arch_design": {
        "cursor": 0.3,
        "gemini": 0.7   # Gemini opinion matters most for design
    }
}
```

If the Weighted Score is below the threshold (7.0/10), the specialized agent wins. In a Security dispute, Cursor's rejection will block the merge even if Gemini loves the code.

---

## 🛡️ TDD Strict Mode

Most AI coding tools write code, and then maybe write a test.
**Conductor flips this.**

1.  **Constraint**: The `Implementer` agent is **physically unable** to write `src/code.py` until a `tests/test_code.py` file exists and is failing.
2.  **Verification**: We run the tests in a sandbox. The Agent cannot simply "say" the tests passed. The system parses the JUnit XML output from the test runner.

---

## 🔄 The Fixer Loop (Self-Healing)

If a test fails, we do not annoy the human immediately.
The **Fixer Agent** wakes up.

1.  **Read Error**: Parses the stack trace.
2.  **Hypothesize**: "I think I missed an import."
3.  **Patch**: Apply the fix.
4.  **Retry**: Run tests again.

It gets **3 lives**. If it fails 3 times, it pauses and alerts the human via the CLI.
