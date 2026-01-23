# The 4-Eyes Protocol

The core security guarantee of Conductor is the **4-Eyes Protocol**.
No single AI model is trusted to write and approve its own code.

---

## 🛡️ The Concept

Every Code Change must be:
1.  **Written** by one Agent (e.g., Claude).
2.  **Verified** by two *other* Agents (e.g., Cursor & Gemini).

This mimics high-security human engineering teams where "Self-Approval" is banned.

---

## 👥 The Roles

| Role | Primary Agent | Lens |
|------|--------------|------|
| **Author** | Claude (A04) | "Make it work." |
| **Reviewer 1** | Cursor (A07) | "Is it safe?" (Security) |
| **Reviewer 2** | Gemini (A08) | "Is it well-designed?" (Architecture) |

---

## 🚦 The Approval Matrix

Once the code passes tests, the Reviewers run in parallel.

### Scenario A: Clean Pass
*   Cursor: ✅ APPROVE (Score 9/10)
*   Gemini: ✅ APPROVE (Score 8/10)
*   **Result**: MERGED.

### Scenario B: Hard Block
*   Cursor: ❌ REJECT (Critical SQL Injection found)
*   Gemini: ✅ APPROVE (Code looks clean)
*   **Result**: **REJECTED**.
    *   *Reason*: A Critical Security Block vetoes everything.

### Scenario C: The Grey Area (Conflict)
*   Cursor: ⚠️ CONCERN (Score 6/10) - "Dependencies look heavy."
*   Gemini: ✅ APPROVE (Score 9/10) - "Architecture is perfect."
*   **Result**: **WEIGHTED VOTING**.

---

## ⚖️ Weighted Conflict Resolution

We do not treat all opinions equally. We trust specific agents for specific domains.

### The Algorithm

$$ FinalScore = (Score_A \times Weight_A) + (Score_B \times Weight_B) $$

#### Weights Table

| Dispute Type | Cursor Weight (Security) | Gemini Weight (Arch) |
|--------------|--------------------------|----------------------|
| **Security Risk** | **0.9** (Trust Cursor) | 0.1 |
| **Code Style** | 0.3 | **0.7** (Trust Gemini) |
| **Performance** | 0.4 | **0.6** |
| **General** | 0.5 | 0.5 |

### Example Resolution
*Dispute: "Is this auth pattern secure?"*
*   Cursor says **NO** (Score 2/10).
*   Gemini says **YES** (Score 9/10).

$$ Score = (2 \times 0.9) + (9 \times 0.1) = 1.8 + 0.9 = 2.7 $$

**Result**: 2.7 is well below the threshold (7.0). **REJECTED.**
The Security Specialist overruled the Generalist.

---

## 📝 Review Artifacts

Every review generates a JSON artifact for the audit trail:

```json
{
  "task_id": "T101",
  "verifiers": ["A07", "A08"],
  "outcome": "REJECTED",
  "blocking_finding": {
    "agent": "A07",
    "severity": "CRITICAL",
    "description": "Hardcoded API Key in src/config.py"
  }
}
```
