#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

SUPPORTED_EXTS = {".ts", ".tsx", ".js", ".jsx", ".json", ".css", ".scss", ".md", ".yaml", ".yml"}
SKIP_DIRS = {"node_modules", "dist", "build", ".next", ".turbo"}


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
    return current


def has_prettier_config(root: Path) -> bool:
    config_names = [
        ".prettierrc",
        ".prettierrc.json",
        ".prettierrc.yml",
        ".prettierrc.yaml",
        ".prettierrc.js",
        ".prettierrc.cjs",
        "prettier.config.js",
        "prettier.config.cjs",
    ]
    if any((root / name).exists() for name in config_names):
        return True
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        if "prettier" in data:
            return True
        deps = data.get("devDependencies", {}) or {}
        deps.update(data.get("dependencies", {}) or {})
        return "prettier" in deps
    return False


def should_format(path: Path) -> bool:
    if path.suffix not in SUPPORTED_EXTS:
        return False
    parts = set(path.parts)
    if parts.intersection(SKIP_DIRS):
        return False
    return True


def run_prettier(root: Path, file_path: Path) -> None:
    # Avoid downloads: only run if prettier is already installed in the repo.
    cmd = ["npx", "--no-install", "prettier", "--write", str(file_path)]
    subprocess.run(cmd, cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    raw_path = payload.get("file_path")
    if not raw_path:
        return 0

    file_path = Path(raw_path)
    if not should_format(file_path):
        return 0

    root = find_repo_root(file_path.parent)
    if not has_prettier_config(root):
        return 0

    run_prettier(root, file_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
