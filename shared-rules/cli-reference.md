# CLI Reference (All Agents)

<!-- SHARED: This file applies to ALL agents -->
<!-- Version: 1.0 -->
<!-- Last Updated: 2026-01-20 -->

## Correct CLI Usage

This is the authoritative reference for CLI tool invocation. Always use these patterns.

---

## Claude Code CLI

**Command**: `claude`

### Non-Interactive Mode
```bash
claude -p "Your prompt here" --output-format json
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `-p` | Prompt (non-interactive) | `-p "What is 2+2?"` |
| `--output-format` | Output format | `--output-format json` |
| `--allowedTools` | Restrict tools | `--allowedTools "Read,Write,Edit"` |
| `--max-turns` | Limit turns | `--max-turns 10` |

### Full Example
```bash
claude -p "Analyze this code" \
    --output-format json \
    --allowedTools "Read,Grep,Glob" \
    --max-turns 5
```

---

## Cursor Agent CLI

**Command**: `cursor-agent`

### Non-Interactive Mode
```bash
cursor-agent --print --output-format json "Your prompt here"
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--print` or `-p` | Non-interactive mode | `--print` |
| `--output-format` | Output format | `--output-format json` |
| `--force` | Skip confirmations | `--force` |

### Prompt Position
**IMPORTANT**: Prompt is a POSITIONAL argument at the END, not a flag value.

### Full Example
```bash
cursor-agent --print \
    --output-format json \
    --force \
    "Review this code for security issues"
```

### Common Mistakes
- `cursor-agent -p "prompt"` - Wrong! `-p` means `--print`, not prompt
- Prompt must be LAST argument

---

## Gemini CLI

**Command**: `gemini`

### Non-Interactive Mode
```bash
gemini --yolo "Your prompt here"
```

### Key Flags
| Flag | Purpose | Example |
|------|---------|---------|
| `--yolo` | Auto-approve tool calls | `--yolo` |
| `--model` | Select model | `--model gemini-2.0-flash` |

### Important Notes
- Gemini does NOT support `--output-format`
- Output must be wrapped in JSON externally if needed
- Prompt is a positional argument

### Full Example
```bash
gemini --model gemini-2.0-flash \
    --yolo \
    "Review architecture of this system"
```

### Common Mistakes
- `gemini --output-format json` - Wrong! Flag doesn't exist
- `gemini -p "prompt"` - Wrong! No `-p` flag

---

## Python Orchestrator

**Command**: `python -m orchestrator`

### Commands
```bash
# Start new workflow
python -m orchestrator --start

# Resume interrupted workflow
python -m orchestrator --resume

# Check health/prerequisites
python -m orchestrator --health

# Initialize missing files
python -m orchestrator --init
```

---

## Shell Script Wrappers

### call-cursor.sh
```bash
bash scripts/call-cursor.sh <prompt-file> <output-file> [project-dir]
```

### call-gemini.sh
```bash
bash scripts/call-gemini.sh <prompt-file> <output-file> [project-dir]
```

### Environment Variables
```bash
export CURSOR_MODEL=gpt-4.5-turbo    # Override Cursor model
export GEMINI_MODEL=gemini-2.0-flash  # Override Gemini model
```

---

## Quick Reference Table

| Tool | Non-Interactive | Prompt | Output Format |
|------|-----------------|--------|---------------|
| `claude` | `-p "prompt"` | Part of `-p` | `--output-format json` |
| `cursor-agent` | `--print` | Positional (end) | `--output-format json` |
| `gemini` | `--yolo` | Positional | N/A (wrap externally) |
