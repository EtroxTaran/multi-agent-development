#!/usr/bin/env python3
"""
Compile agent prompts from templates and agent-specific content.

This script combines:
1. Shared template sections (identity, workflow, error handling, etc.)
2. Type-specific templates (writer, reviewer, planner)
3. Agent-specific PROMPT.md content

To generate the final context files (CLAUDE.md, GEMINI.md, CURSOR-RULES.md).

Usage:
    python scripts/compile-agent-prompts.py           # Compile all agents
    python scripts/compile-agent-prompts.py A04      # Compile specific agent
    python scripts/compile-agent-prompts.py --check  # Verify without writing
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


# Agent metadata from registry
AGENT_METADATA = {
    "A01": {
        "name": "Planner",
        "template_type": "planner",
        "primary_cli": "claude",
        "output_file": "CLAUDE.md",
        "mission": "Break down features into small, testable tasks with dependencies",
        "phase": "Phase 1 - Planning",
        "upstream": "Orchestrator (PRODUCT.md)",
        "downstream": "A02 (reviews), then implementation agents",
        "reviewers": "A08 (Code Reviewer), A02 (Architect)",
        "can_write": "No",
        "can_read": "Yes",
        "allowed_paths": "- None (read-only)",
        "forbidden_paths": "- src/**/*\n- tests/**/*\n- *.py, *.ts, *.js",
        "max_iterations": 3,
    },
    "A02": {
        "name": "Architect",
        "template_type": "reviewer",
        "primary_cli": "gemini",
        "output_file": "GEMINI.md",
        "mission": "Review architectural decisions and system design",
        "phase": "Phase 2 - Validation, Phase 4 - Verification",
        "upstream": "A01 (plans), Implementation agents (code)",
        "downstream": "Orchestrator (approval decision)",
        "reviewers": "None (top-level reviewer)",
        "can_write": "No",
        "can_read": "Yes",
        "allowed_paths": "- None (read-only)",
        "forbidden_paths": "- **/* (read-only agent)",
        "max_iterations": 2,
    },
    "A03": {
        "name": "Test Writer",
        "template_type": "writer",
        "primary_cli": "claude",
        "output_file": "CLAUDE.md",
        "mission": "Write failing tests first following TDD principles",
        "phase": "Phase 3 - Implementation (before A04)",
        "upstream": "A01 (Planner) assigns tasks",
        "downstream": "A04 (Implementer) makes tests pass",
        "reviewers": "A08 (Code Reviewer), A07 (Security Reviewer)",
        "can_write": "Yes",
        "can_read": "Yes",
        "allowed_paths": "- tests/**/*\n- test/**/*\n- spec/**/*\n- *.test.*\n- *.spec.*",
        "forbidden_paths": "- src/**/*\n- lib/**/*\n- app/**/*",
        "max_iterations": 3,
    },
    "A04": {
        "name": "Implementer",
        "template_type": "writer",
        "primary_cli": "claude",
        "output_file": "CLAUDE.md",
        "mission": "Write minimal code to make failing tests pass",
        "phase": "Phase 3 - Implementation (after A03)",
        "upstream": "A03 (Test Writer) provides failing tests",
        "downstream": "A07, A08 (review code)",
        "reviewers": "A07 (Security Reviewer), A08 (Code Reviewer)",
        "can_write": "Yes",
        "can_read": "Yes",
        "allowed_paths": "- src/**/*\n- lib/**/*\n- app/**/*\n- *.py, *.ts, *.js",
        "forbidden_paths": "- tests/**/*\n- test/**/*\n- *.md\n- .workflow/**/*",
        "max_iterations": 3,
    },
    "A05": {
        "name": "Bug Fixer",
        "template_type": "writer",
        "primary_cli": "cursor",
        "output_file": "CURSOR-RULES.md",
        "mission": "Diagnose and fix bugs with root cause analysis",
        "phase": "Phase 3 - Implementation (bug fixing)",
        "upstream": "Bug reports, A10 escalations",
        "downstream": "A07, A08 (review fixes)",
        "reviewers": "A10 (Integration Tester), A08 (Code Reviewer)",
        "can_write": "Yes",
        "can_read": "Yes",
        "allowed_paths": "- src/**/*\n- lib/**/*\n- tests/**/*",
        "forbidden_paths": "- *.md\n- .workflow/**/*",
        "max_iterations": 5,
    },
    "A06": {
        "name": "Refactorer",
        "template_type": "writer",
        "primary_cli": "gemini",
        "output_file": "GEMINI.md",
        "mission": "Refactor code while keeping all tests passing",
        "phase": "Phase 3 - Implementation (refactoring)",
        "upstream": "A08 identifies refactoring needs",
        "downstream": "A07, A08 (review changes)",
        "reviewers": "A08 (Code Reviewer), A07 (Security Reviewer)",
        "can_write": "Yes",
        "can_read": "Yes",
        "allowed_paths": "- src/**/*\n- lib/**/*\n- app/**/*",
        "forbidden_paths": "- tests/**/*\n- *.md\n- .workflow/**/*",
        "max_iterations": 3,
    },
    "A07": {
        "name": "Security Reviewer",
        "template_type": "reviewer",
        "primary_cli": "cursor",
        "output_file": "CURSOR-RULES.md",
        "mission": "Review code for OWASP Top 10 and security vulnerabilities",
        "phase": "Phase 2 - Validation, Phase 4 - Verification",
        "upstream": "Implementation agents submit code",
        "downstream": "Orchestrator (approval decision)",
        "reviewers": "None (top-level reviewer)",
        "can_write": "No",
        "can_read": "Yes",
        "allowed_paths": "- None (read-only)",
        "forbidden_paths": "- **/* (read-only agent)",
        "max_iterations": 2,
    },
    "A08": {
        "name": "Code Reviewer",
        "template_type": "reviewer",
        "primary_cli": "gemini",
        "output_file": "GEMINI.md",
        "mission": "Review code quality, patterns, and best practices",
        "phase": "Phase 2 - Validation, Phase 4 - Verification",
        "upstream": "Implementation agents submit code",
        "downstream": "Orchestrator (approval decision)",
        "reviewers": "None (top-level reviewer)",
        "can_write": "No",
        "can_read": "Yes",
        "allowed_paths": "- None (read-only)",
        "forbidden_paths": "- **/* (read-only agent)",
        "max_iterations": 2,
    },
    "A09": {
        "name": "Documentation Writer",
        "template_type": "writer",
        "primary_cli": "claude",
        "output_file": "CLAUDE.md",
        "mission": "Write and maintain clear, accurate documentation",
        "phase": "Phase 3 - Implementation (documentation)",
        "upstream": "A01 (Planner) assigns documentation tasks",
        "downstream": "A08, A01 (review docs)",
        "reviewers": "A08 (Code Reviewer), A01 (Planner)",
        "can_write": "Yes",
        "can_read": "Yes",
        "allowed_paths": "- docs/**/*\n- *.md\n- README*",
        "forbidden_paths": "- src/**/*\n- tests/**/*\n- *.py, *.ts",
        "max_iterations": 2,
    },
    "A10": {
        "name": "Integration Tester",
        "template_type": "writer",
        "primary_cli": "claude",
        "output_file": "CLAUDE.md",
        "mission": "Write integration, E2E, and BDD tests",
        "phase": "Phase 3 - Implementation (integration testing)",
        "upstream": "A01 (Planner) assigns test tasks",
        "downstream": "A07, A08 (review tests)",
        "reviewers": "A07 (Security Reviewer), A08 (Code Reviewer)",
        "can_write": "Yes",
        "can_read": "Yes",
        "allowed_paths": "- tests/**/*\n- test/**/*\n- e2e/**/*\n- features/**/*\n- *.feature",
        "forbidden_paths": "- src/**/*\n- lib/**/*\n- app/**/*",
        "max_iterations": 3,
    },
    "A11": {
        "name": "DevOps Engineer",
        "template_type": "writer",
        "primary_cli": "cursor",
        "output_file": "CURSOR-RULES.md",
        "mission": "Manage CI/CD, Docker, and infrastructure as code",
        "phase": "Phase 3 - Implementation (infrastructure)",
        "upstream": "A01 (Planner) assigns DevOps tasks",
        "downstream": "A07, A08 (review configs)",
        "reviewers": "A07 (Security Reviewer), A08 (Code Reviewer)",
        "can_write": "Yes",
        "can_read": "Yes",
        "allowed_paths": "- .github/**/*\n- Dockerfile*\n- docker-compose*\n- *.yaml, *.yml\n- Makefile\n- scripts/**/*",
        "forbidden_paths": "- src/**/*\n- tests/**/*",
        "max_iterations": 3,
    },
    "A12": {
        "name": "UI Designer",
        "template_type": "writer",
        "primary_cli": "claude",
        "output_file": "CLAUDE.md",
        "mission": "Create and refine UI components with accessibility",
        "phase": "Phase 3 - Implementation (UI)",
        "upstream": "A01 (Planner) assigns UI tasks",
        "downstream": "A08, A07 (review components)",
        "reviewers": "A08 (Code Reviewer), A07 (Security Reviewer)",
        "can_write": "Yes",
        "can_read": "Yes",
        "allowed_paths": "- src/components/**/*\n- src/ui/**/*\n- src/styles/**/*\n- *.css, *.scss, *.tsx",
        "forbidden_paths": "- tests/**/*\n- *.md\n- .workflow/**/*",
        "max_iterations": 3,
    },
}


# Explicit mapping of agent IDs to directory names
AGENT_DIRS = {
    "A01": "A01-planner",
    "A02": "A02-architect",
    "A03": "A03-test-writer",
    "A04": "A04-implementer",
    "A05": "A05-bug-fixer",
    "A06": "A06-refactorer",
    "A07": "A07-security-reviewer",
    "A08": "A08-code-reviewer",
    "A09": "A09-documentation",
    "A10": "A10-integration-tester",
    "A11": "A11-devops",
    "A12": "A12-ui-designer",
}


def get_agent_dir(agents_dir: Path, agent_id: str) -> Path:
    """Get the directory path for an agent."""
    dir_name = AGENT_DIRS.get(agent_id)
    if not dir_name:
        raise ValueError(f"Unknown agent ID: {agent_id}")
    return agents_dir / dir_name


def load_template_section(templates_dir: Path, section_name: str) -> str:
    """Load a template section file."""
    section_path = templates_dir / "sections" / f"{section_name}.md"
    if section_path.exists():
        return section_path.read_text()
    return f"<!-- Section {section_name} not found -->"


def load_agent_prompt(agents_dir: Path, agent_id: str) -> str:
    """Load agent-specific PROMPT.md content."""
    agent_dir = get_agent_dir(agents_dir, agent_id)
    prompt_path = agent_dir / "PROMPT.md"
    if prompt_path.exists():
        return prompt_path.read_text()
    return f"<!-- Agent {agent_id} PROMPT.md not found -->"


def substitute_variables(content: str, variables: dict[str, Any]) -> str:
    """Substitute {{VARIABLE}} placeholders in content."""
    result = content
    for key, value in variables.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(value))
    return result


def compile_agent_prompt(
    agent_id: str,
    templates_dir: Path,
    agents_dir: Path,
) -> str:
    """Compile a complete agent prompt from templates and agent-specific content."""
    metadata = AGENT_METADATA[agent_id]

    # Load shared sections
    identity_section = load_template_section(templates_dir, "identity")
    workflow_section = load_template_section(templates_dir, "workflow-context")
    completion_section = load_template_section(templates_dir, "completion-signaling")
    error_section = load_template_section(templates_dir, "error-handling")
    quality_section = load_template_section(templates_dir, "quality-checklist")
    boundaries_section = load_template_section(templates_dir, "boundaries")

    # Load type-specific template
    template_type = metadata["template_type"]
    type_template_path = templates_dir / f"{template_type}-agent.md.template"
    type_template = ""
    if type_template_path.exists():
        type_template = type_template_path.read_text()

    # Load agent-specific content
    agent_prompt = load_agent_prompt(agents_dir, agent_id)

    # Extract few-shot examples from agent prompt
    few_shot_examples = ""
    few_shot_match = re.search(r"## Few-Shot Examples\n(.+?)(?=\n## |$)", agent_prompt, re.DOTALL)
    if few_shot_match:
        few_shot_examples = f"# Few-Shot Examples\n{few_shot_match.group(1)}"

    # Extract anti-patterns from type template
    anti_patterns = ""
    anti_match = re.search(r"## Anti-Patterns.*?\n(.+?)(?=\n## |$)", type_template, re.DOTALL)
    if anti_match:
        anti_patterns = f"# Anti-Patterns\n{anti_match.group(1)}"

    # Extract input/output specs from type template
    input_spec = ""
    input_match = re.search(r"## Input Specification.*?\n(.+?)(?=\n## |$)", type_template, re.DOTALL)
    if input_match:
        input_spec = f"# Input Specification\n{input_match.group(1)}"

    output_spec = ""
    output_match = re.search(r"## Output Specification.*?\n(.+?)(?=\n## |$)", type_template, re.DOTALL)
    if output_match:
        output_spec = f"# Output Specification\n{output_match.group(1)}"

    task_instructions = ""
    task_match = re.search(r"## Task Instructions.*?\n(.+?)(?=\n## |$)", type_template, re.DOTALL)
    if task_match:
        task_instructions = f"# Task Instructions\n{task_match.group(1)}"

    # Variables for substitution
    variables = {
        "AGENT_ID": agent_id,
        "AGENT_NAME": metadata["name"],
        "PRIMARY_CLI": metadata["primary_cli"],
        "MISSION": metadata["mission"],
        "PHASE": metadata["phase"],
        "UPSTREAM_AGENTS": metadata["upstream"],
        "DOWNSTREAM_AGENTS": metadata["downstream"],
        "REVIEWERS": metadata["reviewers"],
        "CAN_WRITE": metadata["can_write"],
        "CAN_READ": metadata["can_read"],
        "ALLOWED_PATHS": metadata["allowed_paths"],
        "FORBIDDEN_PATHS": metadata["forbidden_paths"],
        "MAX_ITERATIONS": metadata["max_iterations"],
        "TEMPLATE_TYPE": template_type,
        "COMPILE_DATE": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Substitute variables in all sections
    identity_section = substitute_variables(identity_section, variables)
    workflow_section = substitute_variables(workflow_section, variables)
    completion_section = substitute_variables(completion_section, variables)
    error_section = substitute_variables(error_section, variables)
    quality_section = substitute_variables(quality_section, variables)
    boundaries_section = substitute_variables(boundaries_section, variables)
    input_spec = substitute_variables(input_spec, variables)
    output_spec = substitute_variables(output_spec, variables)
    task_instructions = substitute_variables(task_instructions, variables)
    anti_patterns = substitute_variables(anti_patterns, variables)

    # Assemble final prompt
    sections = [
        f"# {agent_id} {metadata['name']} Agent",
        "",
        f"<!-- AUTO-GENERATED: Do not edit directly -->",
        f"<!-- Template: {template_type} -->",
        f"<!-- Last compiled: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} -->",
        "",
        "---",
        "",
        identity_section,
        "",
        "---",
        "",
        workflow_section,
        "",
        "---",
        "",
        input_spec if input_spec else "<!-- No input specification -->",
        "",
        "---",
        "",
        task_instructions if task_instructions else "<!-- No task instructions -->",
        "",
        "---",
        "",
        output_spec if output_spec else "<!-- No output specification -->",
        "",
        "---",
        "",
        completion_section,
        "",
        "---",
        "",
        error_section,
        "",
        "---",
        "",
        anti_patterns if anti_patterns else "<!-- No anti-patterns defined -->",
        "",
        "---",
        "",
        boundaries_section,
        "",
        "---",
        "",
        quality_section,
        "",
        "---",
        "",
        few_shot_examples if few_shot_examples else "<!-- No examples defined -->",
    ]

    return "\n".join(sections)


def compile_and_write(
    agent_id: str,
    templates_dir: Path,
    agents_dir: Path,
    check_only: bool = False,
) -> bool:
    """Compile an agent prompt and optionally write it."""
    metadata = AGENT_METADATA[agent_id]
    agent_dir = get_agent_dir(agents_dir, agent_id)
    output_path = agent_dir / metadata["output_file"]

    try:
        compiled = compile_agent_prompt(agent_id, templates_dir, agents_dir)

        if check_only:
            print(f"  {agent_id}: OK (would write {len(compiled)} bytes to {output_path.name})")
            return True

        output_path.write_text(compiled)
        print(f"  {agent_id}: Wrote {len(compiled)} bytes to {output_path.name}")
        return True

    except Exception as e:
        print(f"  {agent_id}: ERROR - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Compile agent prompts from templates")
    parser.add_argument(
        "agents",
        nargs="*",
        help="Specific agent IDs to compile (e.g., A04 A07). If empty, compiles all.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify compilation without writing files",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Project root directory",
    )

    args = parser.parse_args()

    templates_dir = args.root / "agents" / "_templates"
    agents_dir = args.root / "agents"

    # Validate directories exist
    if not templates_dir.exists():
        print(f"Error: Templates directory not found: {templates_dir}")
        sys.exit(1)

    if not agents_dir.exists():
        print(f"Error: Agents directory not found: {agents_dir}")
        sys.exit(1)

    # Determine which agents to compile
    agents_to_compile = args.agents if args.agents else list(AGENT_METADATA.keys())

    # Validate agent IDs
    invalid_agents = [a for a in agents_to_compile if a not in AGENT_METADATA]
    if invalid_agents:
        print(f"Error: Unknown agent IDs: {invalid_agents}")
        print(f"Valid agents: {list(AGENT_METADATA.keys())}")
        sys.exit(1)

    print(f"{'Checking' if args.check else 'Compiling'} {len(agents_to_compile)} agents...")

    success_count = 0
    for agent_id in sorted(agents_to_compile):
        if compile_and_write(agent_id, templates_dir, agents_dir, args.check):
            success_count += 1

    print(f"\n{'Checked' if args.check else 'Compiled'} {success_count}/{len(agents_to_compile)} agents successfully")

    if success_count < len(agents_to_compile):
        sys.exit(1)


if __name__ == "__main__":
    main()
