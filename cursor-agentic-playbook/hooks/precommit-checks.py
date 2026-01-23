#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return result.returncode, result.stdout.strip()


def git_root(cwd: Path) -> Path:
    code, out = run(["git", "rev-parse", "--show-toplevel"], cwd)
    if code == 0 and out:
        return Path(out)
    return cwd


def detect_package_manager(pkg: dict) -> str:
    pkg_manager = str(pkg.get("packageManager", "")).lower()
    if pkg_manager.startswith("pnpm"):
        return "pnpm"
    if pkg_manager.startswith("yarn"):
        return "yarn"
    return "npm"


def should_check(command: str) -> bool:
    lower = command.lower()
    return "git commit" in lower


def find_package_json(root: Path) -> Optional[Path]:
    pkg_path = root / "package.json"
    return pkg_path if pkg_path.exists() else None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        print(json.dumps({"permission": "allow"}))
        return 0

    command = (payload.get("command") or "").strip()
    cwd = Path(payload.get("cwd") or os.getcwd())

    if not should_check(command):
        print(json.dumps({"permission": "allow"}))
        return 0

    root = git_root(cwd)
    pkg_path = find_package_json(root)
    if not pkg_path:
        print(
            json.dumps(
                {
                    "permission": "allow",
                    "user_message": "No package.json found; skipping Prettier/TypeScript checks.",
                }
            )
        )
        return 0

    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {}) or {}

    commands: list[list[str]] = []
    runner = detect_package_manager(pkg)

    if "format:check" in scripts:
        commands.append([runner, "run", "format:check"])
    elif "prettier:check" in scripts:
        commands.append([runner, "run", "prettier:check"])
    elif "format" in scripts:
        commands.append([runner, "run", "format"])

    if "lint" in scripts:
        commands.append([runner, "run", "lint"])

    if "typecheck" in scripts:
        commands.append([runner, "run", "typecheck"])

    if not commands:
        print(
            json.dumps(
                {
                    "permission": "allow",
                    "user_message": "No format/lint/typecheck scripts found; skipping checks.",
                }
            )
        )
        return 0

    failures = []
    for cmd in commands:
        code, output = run(cmd, root)
        if code != 0:
            failures.append({"command": " ".join(cmd), "output": output[-2000:]})

    if failures:
        summary = "\n".join(f"- {f['command']}\n  {f['output']}" for f in failures)
        print(
            json.dumps(
                {
                    "permission": "deny",
                    "user_message": "Pre-commit checks failed. Fix issues before committing.",
                    "agent_message": f"Pre-commit checks failed:\n{summary}",
                }
            )
        )
        return 0

    print(
        json.dumps(
            {
                "permission": "allow",
                "user_message": "Pre-commit checks passed (format/lint/typecheck).",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
