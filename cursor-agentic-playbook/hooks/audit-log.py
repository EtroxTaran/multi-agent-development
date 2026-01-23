#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ALLOW_KEYS = {
    "hook_event_name",
    "conversation_id",
    "generation_id",
    "model",
    "file_path",
    "command",
    "cwd",
    "tool_name",
    "duration",
    "status",
    "loop_count",
}

REDACT_PATTERNS = ("api_key", "token", "secret", "password")


def redact_value(value: str) -> str:
    lowered = value.lower()
    if any(pattern in lowered for pattern in REDACT_PATTERNS):
        return "<redacted>"
    return value


def sanitize(payload: dict) -> dict:
    sanitized = {}
    for key in ALLOW_KEYS:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, str):
            sanitized[key] = redact_value(value)
        else:
            sanitized[key] = value
    return sanitized


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    record = sanitize(payload)
    record["timestamp"] = datetime.now(timezone.utc).isoformat()

    logs_dir = Path(os.path.expanduser("~/.cursor/hooks/logs"))
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "agent-audit.jsonl"

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
