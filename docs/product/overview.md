# Conductor: Complete System Guide

**The Definitive Reference for the Multi-Agent Orchestration System**

---

| **Document Info** | |
|-------------------|---|
| Version | 4.1 |
| Last Updated | 2026-01-23 |
| Test Coverage | 1,600+ tests passing |
| Codebase | ~20,000 lines of Python |
| License | Proprietary |

---

## Table of Contents

### For Everyone
1. [Executive Summary](#1-executive-summary)
2. [What Problem Does This Solve?](#2-what-problem-does-this-solve)
3. [Key Capabilities](#3-key-capabilities)

### For Technical Leaders
4. [System Architecture](#4-system-architecture)
5. [The 5-Phase Workflow](#5-the-5-phase-workflow)
6. [Agent Registry (12 Specialists)](#6-agent-registry-12-specialists)
7. [Quality Assurance System](#7-quality-assurance-system)
8. [Universal Agent Loop](#8-universal-agent-loop)

### For Developers
9. [Quick Start Guide](#9-quick-start-guide)
10. [Project Structure](#10-project-structure)
11. [Configuration Reference](#11-configuration-reference)
12. [CLI Commands](#12-cli-commands)
13. [Extending the System](#13-extending-the-system)

### Reference
14. [Error Handling & Recovery](#14-error-handling--recovery)
15. [Security Model](#15-security-model)
16. [Troubleshooting](#16-troubleshooting)
17. [Glossary](#17-glossary)
18. [Appendix: File Reference](#18-appendix-file-reference)

---

# Part I: Overview

## 1. Executive Summary

### What is Conductor?

Conductor is a **production-grade multi-agent orchestration system** that coordinates three AI coding assistants—Claude, Cursor, and Gemini—to automatically implement software features from specification to working code.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   PRODUCT.md ──────► CONDUCTOR ──────► Working Code   │
│   (Your Spec)         (5 Phases)           (Tested & Reviewed)
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Value Proposition

| Benefit | Description |
|---------|-------------|
| **Automated Feature Implementation** | From specification to working code without human coding |
| **Built-in Quality Assurance** | 4-eyes review protocol ensures every change is verified by 2 different AI reviewers |
| **Test-Driven Development** | Tests written first, code written to pass tests—always |
| **Error Recovery** | Automatic retries, checkpointing, and intelligent escalation |
| **Full Auditability** | Complete logging, state tracking, and decision trails |

### By the Numbers

| Metric | Value |
|--------|-------|
| Specialist Agents | 12 |
| Workflow Phases | 5 |
| Test Suite | 1,250+ tests |
| Code Coverage | ~85% |
| Supported AI CLIs | 3 (Claude, Cursor, Gemini) |

### Target Audience

- **Product Teams**: Accelerate feature development with AI-assisted implementation
- **Engineering Leaders**: Maintain quality standards while increasing velocity
- **Solo Developers**: Get expert-level code review on every change

---

## 2. What Problem Does This Solve?

### The Challenge

Traditional AI coding assistants are powerful but have limitations:

| Problem | Impact |
|---------|--------|
| **Single-model bias** | One AI may miss issues another would catch |
| **No quality gates** | Code goes straight to repo without review |
| **Context fragmentation** | Long conversations lose important context |
| **No TDD enforcement** | Tests often written after (or not at all) |
| **Manual coordination** | Developer must orchestrate multiple tools |

### The Solution

Conductor addresses these by:

1. **Multi-Agent Coordination**: Three different AI systems check each other's work
2. **Structured Workflow**: 5-phase process with checkpoints and gates
3. **Enforced TDD**: Tests must exist and pass before code is accepted
4. **4-Eyes Protocol**: Every task verified by 2 different CLI/model combinations
5. **Automated Orchestration**: System handles coordination automatically

### Before vs. After

```
BEFORE (Manual):
  Developer → Write Code → Maybe Test → Maybe Review → Merge

AFTER (Conductor):
  Developer → Write Spec → [Automated: Plan → Validate → Implement TDD → Verify] → Merge
```

---

## 3. Key Capabilities

### 3.1 Automated Feature Implementation

Write a specification, get working code:

```markdown
# In PRODUCT.md:
## Feature Name
User Authentication Service

## Acceptance Criteria
- [ ] Users can register with email
- [ ] Login returns JWT tokens
- [ ] Tokens expire after 15 minutes
```

The system automatically:
1. Creates an implementation plan
2. Writes failing tests first
3. Implements code to pass tests
4. Verifies with security and code review
5. Produces documented, tested, reviewed code

### 3.2 Multi-Agent Verification

Every task is verified by multiple AI systems:

```
Task Complete ──► Cursor (Security Review) ──┐
                                             ├──► Decision
Task Complete ──► Gemini (Code Review) ──────┘
```

### 3.3 Test-Driven Development

TDD is enforced, not optional:

```
1. Write Tests (must fail initially)
2. Implement Code (minimal to pass tests)
3. Refactor (tests must stay green)
```

### 3.4 Checkpoint & Resume

Work is never lost:

```bash
# Resume from where you left off
python -m orchestrator --project my-app --resume
```

### 3.5 Parallel Execution

Independent tasks run simultaneously:

```bash
# Run 3 workers in parallel
./scripts/init.sh run my-app --parallel 3
```

---
