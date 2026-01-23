#!/usr/bin/env python3
"""
Sync shared rules to agent-specific context files.

This script compiles the shared rules from shared-rules/ into the
agent-specific context files (CLAUDE.md, GEMINI.md, .cursor/rules).

Usage:
    python scripts/sync-rules.py              # Sync all agents
    python scripts/sync-rules.py --agent claude  # Sync specific agent
    python scripts/sync-rules.py --dry-run    # Show what would change
    python scripts/sync-rules.py --validate   # Validate rules
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime
from pathlib import Path

# Configuration
SHARED_RULES_DIR = Path("shared-rules")
AGENT_OVERRIDES_DIR = SHARED_RULES_DIR / "agent-overrides"

# Shared rule files in order of inclusion
SHARED_FILES = [
    "core-rules.md",
    "coding-standards.md",
    "guardrails.md",
    "cli-reference.md",
    "lessons-learned.md",
]

# Agent output configuration
AGENTS = {
    "claude": {
        "output": Path("CLAUDE.md"),
        "override": AGENT_OVERRIDES_DIR / "claude.md",
        "header": "# Claude Code Context\n\n",
        "description": "Instructions for Claude Code as lead orchestrator.",
    },
    "gemini": {
        "output": Path("GEMINI.md"),
        "override": AGENT_OVERRIDES_DIR / "gemini.md",
        "header": "# Gemini Agent Context\n\n",
        "description": "Instructions for Gemini as architecture reviewer.",
    },
    "cursor": {
        "output": Path(".cursor/rules/00-general.mdc"),
        "override": AGENT_OVERRIDES_DIR / "cursor.md",
        "header": "# Cursor Agent Rules\n\nglobs: **/*\n\n",
        "description": "Instructions for Cursor as code quality reviewer.",
    },
}


def read_file(path: Path) -> str:
    """Read file contents if it exists."""
    if path.exists():
        return path.read_text()
    return ""


def compute_checksum(content: str) -> str:
    """Compute SHA256 checksum of content."""
    return hashlib.sha256(content.encode()).hexdigest()[:12]


def load_shared_rules() -> str:
    """Load and concatenate all shared rule files."""
    sections = []

    for filename in SHARED_FILES:
        filepath = SHARED_RULES_DIR / filename
        if filepath.exists():
            content = filepath.read_text().strip()
            sections.append(f"\n---\n\n{content}")
        else:
            print(f"Warning: Shared rule file not found: {filepath}")

    return "\n".join(sections)


def load_agent_override(agent: str) -> str:
    """Load agent-specific override rules."""
    config = AGENTS[agent]
    override_path = config["override"]

    if override_path.exists():
        return override_path.read_text().strip()
    return ""

    return "\n".join(parts)


def load_skills() -> str:
    """Load and format skills from .claude/skills directory."""
    skills_dir = Path(".claude/skills")
    if not skills_dir.exists():
        return ""

    skills = []
    for skill_path in skills_dir.glob("*/SKILL.md"):
        content = skill_path.read_text()
        lines = content.splitlines()

        # Parse frontmatter
        meta = {}
        if lines[0] == "---":
            for line in lines[1:]:
                if line == "---":
                    break
                if ":" in line:
                    key, val = line.split(":", 1)
                    meta[key.strip()] = val.strip().strip('"').strip("'")

        # Fallback if no frontmatter or missing keys
        name = meta.get("name", skill_path.parent.name)
        desc = meta.get("description", "No description provided")

        # Infer command from name if not explicit
        # We assume command is /<name> for now, or check typical patterns
        command = f"/{name}"
        if name == "frontend-dev-guidelines":
            command = "n/a"

        skills.append(f"| {name.upper()} | {command} | {desc} |")

    if not skills:
        return ""

    # Sort by name
    skills.sort()

    header = [
        "\n## Available Skills\n",
        "The following skills are available for use via the specified commands:\n",
        "| Skill | Command | Description |",
        "|-------|---------|-------------|",
    ]

    return "\n".join(header + skills) + "\n"


def sync_cursor_rules(dry_run: bool = False) -> int:
    """Generate .mdc rule files for Cursor."""
    skills_dir = Path(".claude/skills")
    cursor_rules_dir = Path(".cursor/rules/generated-skills")

    if not skills_dir.exists():
        return 0

    if not dry_run:
        cursor_rules_dir.mkdir(parents=True, exist_ok=True)
        # Clear existing generated rules to handle renames/deletions
        for existing in cursor_rules_dir.glob("*.mdc"):
            existing.unlink()

    count = 0
    for skill_path in skills_dir.glob("*/SKILL.md"):
        content = skill_path.read_text()

        # Parse frontmatter to get description for Cursor routing
        description = "Agent Skill"
        lines = content.splitlines()
        if lines[0] == "---":
            for line in lines[1:]:
                if line == "---":
                    break
                if line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()

        # Create MDC content with Cursor-specific frontmatter
        skill_name = skill_path.parent.name

        # We wrap the content in a new MDC format
        # glob: **/* means it's available everywhere, but description helps routing
        mdc_content = f"""---
description: {description}
globs: **/*
---
<!-- AUTO-GENERATED from .claude/skills/{skill_name}/SKILL.md -->
{content}
"""
        target_path = cursor_rules_dir / f"{skill_name}.mdc"

        if dry_run:
            print(f"  cursor: Would generate {target_path}")
        else:
            target_path.write_text(mdc_content)

        count += 1

    return count


def sync_claude_commands(dry_run: bool = False) -> int:
    """Generate symlinks for Claude Code slash commands."""
    skills_dir = Path(".claude/skills")
    commands_dir = Path(".claude/commands")

    if not skills_dir.exists():
        return 0

    if not dry_run:
        commands_dir.mkdir(parents=True, exist_ok=True)
        # We don't clear everything here to assume user might have manual commands
        # But we should really separate generated ones? For now, we overwrite namesakes.

    count = 0
    # Current script runs from root, so relative path is needed for symlink
    # Link: .claude/commands/<name>.md -> ../skills/<name>/SKILL.md

    for skill_path in skills_dir.glob("*/SKILL.md"):
        skill_name = skill_path.parent.name
        target_link = commands_dir / f"{skill_name}.md"

        # Calculate relative path: ../skills/<name>/SKILL.md
        rel_path = Path("..") / "skills" / skill_name / "SKILL.md"

        if dry_run:
            print(f"  claude: Would link {target_link} -> {rel_path}")
            count += 1
            continue

        if target_link.exists() or target_link.is_symlink():
            target_link.unlink()

        target_link.symlink_to(rel_path)
        count += 1

    return count


def generate_agent_file(agent: str, shared_rules: str) -> str:
    """Generate the complete agent context file."""
    config = AGENTS[agent]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build the file
    parts = [
        config["header"],
        "<!-- AUTO-GENERATED from shared-rules/ -->",
        f"<!-- Last synced: {timestamp} -->",
        "<!-- DO NOT EDIT - Run: python scripts/sync-rules.py -->",
        f"\n{config['description']}\n",
    ]

    # Add agent-specific rules first
    agent_override = load_agent_override(agent)
    if agent_override:
        parts.append(f"\n{agent_override}\n")

    # Add Skills Registry
    skills_section = load_skills()
    if skills_section:
        parts.append(skills_section)

    # Add shared rules section
    parts.append("\n---\n")
    parts.append("\n# Shared Rules\n")
    parts.append("\nThe following rules apply to all agents in the workflow.\n")
    parts.append(shared_rules)

    return "\n".join(parts)


def sync_agent(agent: str, shared_rules: str, dry_run: bool = False) -> bool:
    """Sync rules to a specific agent's context file."""
    config = AGENTS[agent]
    output_path = config["output"]

    # Generate new content
    new_content = generate_agent_file(agent, shared_rules)
    new_checksum = compute_checksum(new_content)

    # Read existing content
    old_content = read_file(output_path)
    old_checksum = compute_checksum(old_content) if old_content else "none"

    # Check if changed
    if new_checksum == old_checksum:
        print(f"  {agent}: No changes")
        return False

    if dry_run:
        print(f"  {agent}: Would update {output_path}")
        print(f"    Old checksum: {old_checksum}")
        print(f"    New checksum: {new_checksum}")
        return True

    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write new content
    output_path.write_text(new_content)
    print(f"  {agent}: Updated {output_path}")
    print(f"    Checksum: {new_checksum}")

    return True


def validate_rules() -> bool:
    """Validate all rule files for consistency."""
    print("Validating rules...\n")
    errors = []
    warnings = []

    # Check shared files exist
    for filename in SHARED_FILES:
        filepath = SHARED_RULES_DIR / filename
        if not filepath.exists():
            errors.append(f"Missing shared rule: {filepath}")

    # Check agent overrides exist
    for agent, config in AGENTS.items():
        override_path = config["override"]
        if not override_path.exists():
            warnings.append(f"Missing agent override: {override_path}")

    # Check for version markers
    for filename in SHARED_FILES:
        filepath = SHARED_RULES_DIR / filename
        if filepath.exists():
            content = filepath.read_text()
            if "<!-- Version:" not in content:
                warnings.append(f"Missing version marker: {filepath}")

    # Report results
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  - {e}")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  - {w}")

    if not errors and not warnings:
        print("All rules valid!")

    return len(errors) == 0


def main():
    parser = argparse.ArgumentParser(description="Sync shared rules to agent context files")
    parser.add_argument(
        "--agent",
        choices=list(AGENTS.keys()),
        help="Sync specific agent only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate rules without syncing",
    )

    args = parser.parse_args()

    # Change to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)

    # Validate mode
    if args.validate:
        valid = validate_rules()
        sys.exit(0 if valid else 1)

    print("Syncing shared rules to agent files...\n")

    # Load shared rules
    shared_rules = load_shared_rules()

    # Sync agents
    agents_to_sync = [args.agent] if args.agent else list(AGENTS.keys())
    updated = 0

    for agent in agents_to_sync:
        if sync_agent(agent, shared_rules, args.dry_run):
            updated += 1

    # Sync Skills (Cursor MDC + Claude Commands)
    # We always do this unless a specific agent is requested (optional, but let's just do it)
    if not args.agent or args.agent == "cursor":
        print("\nSyncing Cursor Rules (.mdc)...")
        cursor_count = sync_cursor_rules(args.dry_run)
        if args.dry_run:
            print(f"  Would generate {cursor_count} .mdc files")
        else:
            print(f"  Generated {cursor_count} .mdc files")

    if not args.agent or args.agent == "claude":
        print("\nSyncing Claude Commands (symlinks)...")
        claude_count = sync_claude_commands(args.dry_run)
        if args.dry_run:
            print(f"  Would create {claude_count} symlinks")
        else:
            print(f"  Created {claude_count} symlinks")

    # Summary
    print()
    if args.dry_run:
        print(f"Dry run complete. {updated} file(s) would be updated.")
    else:
        print(f"Sync complete. {updated} file(s) updated.")


if __name__ == "__main__":
    main()
