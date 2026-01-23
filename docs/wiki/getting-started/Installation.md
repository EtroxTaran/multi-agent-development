# Installation & CLI Reference

## 📥 Installation

### Prerequisites
*   Python 3.12 or higher.
*   Node.js (for Claude Code / Gemini CLI wrappers).
*   `git`.

### Setup
1.  **Clone the Repo**:
    ```bash
    git clone https://github.com/your/repo.git
    cd repo
    ```
2.  **Install Python Dependencies**:
    ```bash
    pip install -r requirements.txt
    # OR using uv
    uv sync
    ```
3.  **Install AI CLIs**:
    ```bash
    npm install -g @anthropic-ai/claude-code
    npm install -g @google/gemini-cli
    ```
4.  **Verify**:
    ```bash
    ./scripts/init.sh check
    ```

---

## 💻 CLI Commands

### Project Management

**Initialize a new feature:**
```bash
./scripts/init.sh init <feature_name>
```
Creates `projects/<feature_name>` with the standard template.

**List all active projects:**
```bash
./scripts/init.sh list
```

### Execution

**Run the standard workflow:**
```bash
./scripts/init.sh run <feature_name>
```

**Run in "Parallel Mode" (Faster):**
```bash
./scripts/init.sh run <feature_name> --parallel 3
```
Spawns 3 simultaneous workers using Git Worktrees.

**Resume a paused/crashed workflow:**
```bash
python -m orchestrator --project <feature_name> --resume
```

### debugging

**Check Status:**
```bash
./scripts/init.sh status <feature_name>
```

**View Logs:**
```bash
tail -f projects/<feature_name>/.workflow/coordination.log
```
