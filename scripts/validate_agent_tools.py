#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

REQUIRED_FIELDS = {
    "agent_id",
    "agent_name",
    "description",
    "allowed",
    "forbidden",
    "file_restrictions",
    "budget_limits",
    "timeout_seconds",
    "max_retries",
    "completion_signals",
}

REQUIRED_FILE_RESTRICTIONS = {"allowed_paths", "forbidden_paths", "read_only"}
REQUIRED_BUDGET_LIMITS = {"per_invocation_usd", "per_task_usd", "fallback_model"}


def validate_tools(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return [f"Invalid JSON: {exc}"]

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        errors.append(f"Missing fields: {sorted(missing)}")

    if not isinstance(data.get("allowed"), list):
        errors.append("allowed must be a list.")
    if not isinstance(data.get("forbidden"), list):
        errors.append("forbidden must be a list.")

    file_restrictions = data.get("file_restrictions", {})
    if not REQUIRED_FILE_RESTRICTIONS <= set(file_restrictions.keys()):
        errors.append("file_restrictions must include allowed_paths, forbidden_paths, read_only.")

    budget_limits = data.get("budget_limits", {})
    if not REQUIRED_BUDGET_LIMITS <= set(budget_limits.keys()):
        errors.append(
            "budget_limits must include per_invocation_usd, per_task_usd, fallback_model."
        )

    max_retries = data.get("max_retries")
    if not isinstance(max_retries, int) or not (1 <= max_retries <= 10):
        errors.append("max_retries must be an integer between 1 and 10.")

    timeout = data.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout < 60:
        errors.append("timeout_seconds must be an integer >= 60.")

    completion = data.get("completion_signals", {})
    if not all(key in completion for key in ("claude", "cursor", "gemini")):
        errors.append("completion_signals must include claude, cursor, gemini.")

    return errors


def main() -> int:
    agents_dir = Path("agents")
    failures = 0
    for tools_path in sorted(agents_dir.glob("**/TOOLS.json")):
        errors = validate_tools(tools_path)
        if errors:
            failures += 1
            print(f"[FAIL] {tools_path}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"[OK]   {tools_path}")

    if failures:
        print(f"\nAgent tool validation failed for {failures} file(s).")
        return 1
    print("\nAll agent tool files passed validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
