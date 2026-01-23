#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

REQUIRED_FRONTMATTER = {"name", "description", "version", "tags", "owner", "status"}
STATUS_VALUES = {"active", "experimental", "deprecated"}

SECTION_ALIASES = {
    "overview": {"Overview", "Identity"},
    "usage": {"Usage", "Workflow", "Command"},
    "prerequisites": {"Prerequisites", "Input Requirements", "Prerequisites Check"},
    "steps": {"Workflow Steps", "Execution Steps", "Process", "Workflow"},
    "error_handling": {"Error Handling", "Error Recovery"},
    "examples": {"Examples", "Example", "Example Usage", "Example Output"},
    "outputs": {"Outputs", "Output", "Output Format", "Output Files"},
    "related": {"Related Skills", "Related"},
}


def parse_frontmatter(lines: list[str]) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        return {}, -1
    data: dict[str, str] = {}
    for idx in range(1, len(lines)):
        line = lines[idx].rstrip("\n")
        if line.strip() == "---":
            return data, idx
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return {}, -1


def normalize_tags(value: str) -> list[str]:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip() for item in inner.split(",")]
    return [value]


def headings(lines: list[str]) -> set[str]:
    return {line[3:].strip() for line in lines if line.startswith("## ")}


def validate_skill(path: Path) -> list[str]:
    errors: list[str] = []
    lines = path.read_text().splitlines()
    frontmatter, end_idx = parse_frontmatter(lines)
    if end_idx == -1:
        errors.append("Missing or invalid frontmatter block.")
        return errors

    missing = REQUIRED_FRONTMATTER - set(frontmatter.keys())
    if missing:
        errors.append(f"Missing frontmatter fields: {sorted(missing)}")

    name = frontmatter.get("name", "")
    if name and name != path.parent.name:
        errors.append(f"Frontmatter name '{name}' does not match directory '{path.parent.name}'.")

    version = frontmatter.get("version", "")
    if version and not re.match(r"^[0-9]+\\.[0-9]+\\.[0-9]+$", version):
        errors.append("Version must be semantic (x.y.z).")

    status = frontmatter.get("status", "")
    if status and status not in STATUS_VALUES:
        errors.append(f"Status must be one of {sorted(STATUS_VALUES)}.")

    tags = normalize_tags(frontmatter.get("tags", ""))
    if not tags:
        errors.append("Tags must be a non-empty list.")

    content_lines = lines[end_idx + 1 :]
    found = headings(content_lines)
    for section, aliases in SECTION_ALIASES.items():
        if not (found & aliases):
            errors.append(f"Missing required section for {section}: one of {sorted(aliases)}.")

    return errors


def main() -> int:
    skills_dir = Path(".claude/skills")
    if not skills_dir.exists():
        print("No skills directory found.")
        return 1

    failures = 0
    for skill_path in sorted(skills_dir.glob("*/SKILL.md")):
        errors = validate_skill(skill_path)
        if errors:
            failures += 1
            print(f"[FAIL] {skill_path}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"[OK]   {skill_path}")

    if failures:
        print(f"\nSkill validation failed for {failures} file(s).")
        return 1
    print("\nAll skill files passed validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
