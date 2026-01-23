# Junior Developer Onboarding Guide

## 👋 Welcome to Conductor!

Welcome to the team! If you are reading this, you are probably wondering: **"What exactly *is* Conductor?"**

Don't worry, it looks complex, but the core concept is simple. This guide will walk you through everything you need to know to be productive from Day 1.

---

## 1. What is Conductor?

Imagine if you had 12 senior engineers sitting next to you, ready to help you write code, review your work, check for security bugs, and write tests.

**Conductor is exactly that.** It is a system that manages a team of **AI Agents** (Artificial Intelligence programs) that act like specialized software engineers.

*   **Claude** is your Lead Developer and Planner.
*   **Cursor** is your Security Expert and Bug Fixer.
*   **Gemini** is your Software Architect and Code Reviewer.

Instead of writing every single line of code yourself, you act as the **Product Owner**. You tell Conductor *what* you want (the feature), and Conductor coordinates these AI agents to build it for you.

### Why do we do this?
*   **Speed**: We can build features much faster.
*   **Quality**: Every line of code is reviewed by two different AI "brains" (Cursor and Gemini) before it's finished.
*   **Reliability**: We force "Test-Driven Development" (TDD), which means we write tests *before* the code, ensuring fewer bugs.

---

## 2. Your Role

As a Developer using Conductor, your job shifts from "typing code" to "managing requirements".

| Old Way | Conductor Way |
|---------|---------------|
| You write the code | You write the **Specification** (`PRODUCT.md`) |
| You manually run tests | You watch the agents run tests automatically |
| You ask a human for review | You approve the **Agent Plan** |
| You fix syntax errors | You let the **Fixer Agent** handle routine errors |

**You are the pilot.** The agents are the crew. You set the destination, and they fly the plane.

---

## 3. Getting Set Up

(Ask your lead for the repo access if you haven't already!)

### Prerequisites
*   **Python 3.12+**: The brain of the system.
*   **Git**: For version control.
*   **API Keys**: You'll need keys for Anthropic (Claude) and Google (Gemini). check `1Password` or ask your lead.

### Installation
Run this command in your terminal:
```bash
./scripts/init.sh check
```
If everything is green, you are good to go!

---

## 4. Your First Task: "Hello World"

Let's build a simple feature to see how it works.

1.  **Create a Project**:
    ```bash
    ./scripts/init.sh init my-first-feature
    ```

2.  **Define the Feature**:
    Open `projects/my-first-feature/PRODUCT.md`. This is where you tell the agents what to do. Paste this in:
    ```markdown
    # Feature: Hello World API

    ## Summary
    A simple API endpoint that returns a greeting.

    ## Acceptance Criteria
    - [ ] GET /hello returns "Hello World"
    - [ ] GET /hello/name returns "Hello {name}"
    ```

3.  **Launch Conductor**:
    ```bash
    ./scripts/init.sh run my-first-feature
    ```

4.  **Watch the Magic**:
    *   **Phase 1 (Plan)**: Claude will read your file and propose a plan. *You might need to approve it.*
    *   **Phase 2 (Validate)**: Cursor and Gemini will check the plan for issues.
    *   **Phase 3 (Implement)**: Claude will write tests, see them fail, then write code to pass them.
    *   **Phase 4 (Verify)**: The agents review the code.

5.  **Done!**
    Check the `src/` folder. You'll see code you didn't write, but works perfectly!

---

## 5. Pro-Tips for Success

*   **Be Specific**: The agents are smart, but literal. If you don't say "Handle errors", they might not.
*   **Trust the Process**: Don't try to edit the code while the agents are running. Wait for them to finish.
*   **Review the Reviewers**: When Cursor or Gemini gives feedback, read it! It's a great way to learn best practices.

## 6. Where to go next?
*   [Understanding the Workflow](../workflow/The-5-Phase-Lifecycle.md) - Deep dive into what happens in each phase.
*   [Writing Good Specs](../guides/Writing-Product-Specs.md) - How to write `PRODUCT.md` like a pro.
