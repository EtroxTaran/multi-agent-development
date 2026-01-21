"""Task breakdown node.

Parses PRODUCT.md acceptance criteria into individual tasks
with dependencies, priorities, and milestones for incremental execution.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..state import (
    WorkflowState,
    Task,
    Milestone,
    TaskStatus,
    PhaseStatus,
    PhaseState,
    create_task,
)
from ..integrations import (
    create_linear_adapter,
    save_issue_mapping,
    create_markdown_tracker,
)

logger = logging.getLogger(__name__)

# Priority keywords for classification
PRIORITY_KEYWORDS = {
    "critical": ["critical", "blocker", "must have", "required", "essential"],
    "high": ["high", "important", "should have", "core"],
    "medium": ["medium", "nice to have", "enhancement"],
    "low": ["low", "optional", "future", "nice-to-have"],
}

# Complexity indicators
COMPLEXITY_INDICATORS = {
    "high": ["complex", "multiple", "integration", "refactor", "architecture", "migration"],
    "medium": ["moderate", "several", "update", "extend", "modify"],
    "low": ["simple", "single", "add", "fix", "update", "rename"],
}


async def task_breakdown_node(state: WorkflowState) -> dict[str, Any]:
    """Break down PRODUCT.md into individual tasks.

    Parses the implementation plan and PRODUCT.md to create:
    - Individual tasks with user stories
    - Task dependencies based on file relationships
    - Milestones for grouping related tasks
    - Priority and complexity estimates

    Args:
        state: Current workflow state

    Returns:
        State updates with tasks and milestones
    """
    logger.info(f"Breaking down tasks for: {state['project_name']}")

    project_dir = Path(state["project_dir"])
    plan = state.get("plan", {})

    if not plan:
        return {
            "errors": [{
                "type": "task_breakdown_error",
                "message": "No plan available for task breakdown",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    # Load PRODUCT.md for acceptance criteria
    product_md = _load_product_md(project_dir)
    if not product_md:
        return {
            "errors": [{
                "type": "task_breakdown_error",
                "message": "PRODUCT.md not found",
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    # Parse acceptance criteria from PRODUCT.md
    acceptance_criteria = _parse_acceptance_criteria(product_md)

    # Extract tasks from plan phases
    tasks, milestones = _extract_tasks_from_plan(plan, acceptance_criteria, product_md)

    if not tasks:
        # Create a single task from the plan if no explicit tasks
        tasks = _create_single_task_from_plan(plan, acceptance_criteria)
        milestones = [Milestone(
            id="M1",
            name="Implementation",
            description="Full feature implementation",
            task_ids=[t["id"] for t in tasks],
            status=TaskStatus.PENDING,
        )]

    # Assign dependencies based on file relationships
    tasks = _assign_dependencies(tasks)

    # Detect circular dependencies
    cycles = detect_circular_dependencies(tasks)
    if cycles:
        cycle_details = "; ".join([" -> ".join(cycle) for cycle in cycles[:3]])  # Show first 3
        logger.error(f"Circular dependencies detected: {cycle_details}")
        return {
            "errors": [{
                "type": "circular_dependency_error",
                "message": f"Circular dependencies detected in tasks: {cycle_details}",
                "cycles": cycles,
                "timestamp": datetime.now().isoformat(),
            }],
            "next_decision": "escalate",
        }

    # Save tasks to workflow directory
    tasks_output = {
        "tasks": [dict(t) for t in tasks],
        "milestones": [dict(m) for m in milestones],
        "created_at": datetime.now().isoformat(),
        "source": "task_breakdown_node",
    }

    tasks_dir = project_dir / ".workflow" / "phases" / "task_breakdown"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "tasks.json").write_text(json.dumps(tasks_output, indent=2))

    # Create Linear issues (if configured)
    linear_adapter = create_linear_adapter(project_dir)
    linear_mapping = linear_adapter.create_issues_from_tasks(tasks, state["project_name"])
    if linear_mapping:
        save_issue_mapping(project_dir, linear_mapping)
        logger.info(f"Created {len(linear_mapping)} Linear issues")

    # Create markdown task files (always, if tracking enabled)
    markdown_tracker = create_markdown_tracker(project_dir)
    task_files = markdown_tracker.create_task_files(tasks, linear_mapping)
    if task_files:
        logger.info(f"Created {len(task_files)} markdown task files")

    logger.info(f"Created {len(tasks)} tasks in {len(milestones)} milestones")

    return {
        "tasks": tasks,
        "milestones": milestones,
        "next_decision": "continue",
        "updated_at": datetime.now().isoformat(),
    }


def _load_product_md(project_dir: Path) -> Optional[str]:
    """Load PRODUCT.md content.

    Args:
        project_dir: Project directory path

    Returns:
        PRODUCT.md content or None if not found
    """
    product_md_path = project_dir / "PRODUCT.md"
    if product_md_path.exists():
        return product_md_path.read_text()
    return None


def _parse_acceptance_criteria(product_md: str) -> list[str]:
    """Parse acceptance criteria from PRODUCT.md.

    Looks for:
    - Checklist items (- [ ] or - [x])
    - Numbered lists after "Acceptance Criteria" heading
    - Bullet points after criteria heading

    Args:
        product_md: PRODUCT.md content

    Returns:
        List of acceptance criteria strings
    """
    criteria = []

    # Find acceptance criteria section
    ac_pattern = r"(?:##?\s*)?(?:Acceptance\s*Criteria|Requirements|Criteria)[:\s]*\n((?:[\s\S]*?)(?=\n##|\n\*\*[A-Z]|\Z))"
    ac_match = re.search(ac_pattern, product_md, re.IGNORECASE)

    if ac_match:
        section = ac_match.group(1)

        # Extract checklist items
        checklist = re.findall(r"[-*]\s*\[[x ]\]\s*(.+)", section, re.IGNORECASE)
        criteria.extend(checklist)

        # Extract numbered items
        numbered = re.findall(r"\d+\.\s*(.+)", section)
        criteria.extend(numbered)

        # Extract simple bullet points if no checklist items
        if not criteria:
            bullets = re.findall(r"[-*]\s+(?!\[)(.+)", section)
            criteria.extend(bullets)

    # Also look for definition of done
    dod_pattern = r"(?:##?\s*)?(?:Definition\s*of\s*Done|DoD)[:\s]*\n((?:[\s\S]*?)(?=\n##|\n\*\*[A-Z]|\Z))"
    dod_match = re.search(dod_pattern, product_md, re.IGNORECASE)

    if dod_match:
        section = dod_match.group(1)
        checklist = re.findall(r"[-*]\s*\[[x ]\]\s*(.+)", section, re.IGNORECASE)
        criteria.extend(checklist)

    return [c.strip() for c in criteria if c.strip()]


def _extract_tasks_from_plan(
    plan: dict,
    acceptance_criteria: list[str],
    product_md: str,
) -> tuple[list[Task], list[Milestone]]:
    """Extract tasks from implementation plan phases.

    Args:
        plan: Implementation plan from Phase 1
        acceptance_criteria: Parsed acceptance criteria
        product_md: Raw PRODUCT.md content

    Returns:
        Tuple of (tasks, milestones)
    """
    tasks = []
    milestones = []

    phases = plan.get("phases", [])
    if not phases:
        return [], []

    # Create a milestone for each phase
    for phase in phases:
        phase_num = phase.get("phase", 1)
        phase_name = phase.get("name", f"Phase {phase_num}")
        milestone_id = f"M{phase_num}"

        milestone_task_ids = []
        phase_tasks = phase.get("tasks", [])

        for task_data in phase_tasks:
            task_id = task_data.get("id", f"T{len(tasks) + 1}")
            description = task_data.get("description", "")

            # Generate user story
            user_story = _generate_user_story(description, product_md)

            # Match acceptance criteria to this task
            task_criteria = _match_criteria_to_task(description, acceptance_criteria)

            # Get file information
            files = task_data.get("files", [])
            files_to_create = [f for f in files if "create" in description.lower() or not (Path(f).exists() if Path(f).is_absolute() else False)]
            files_to_modify = [f for f in files if f not in files_to_create]

            # Generate test files
            test_files = _generate_test_files(files, plan)

            # Estimate priority and complexity
            priority = _estimate_priority(description, task_criteria)
            complexity = _estimate_complexity(description, files)

            # Get explicit dependencies from plan
            dependencies = task_data.get("dependencies", [])

            task = create_task(
                task_id=task_id,
                title=description[:80] if len(description) > 80 else description,
                user_story=user_story,
                acceptance_criteria=task_criteria,
                dependencies=dependencies,
                priority=priority,
                milestone_id=milestone_id,
                estimated_complexity=complexity,
                files_to_create=files_to_create,
                files_to_modify=files_to_modify,
                test_files=test_files,
            )

            tasks.append(task)
            milestone_task_ids.append(task_id)

        if milestone_task_ids:
            milestone = Milestone(
                id=milestone_id,
                name=phase_name,
                description=f"Phase {phase_num}: {phase_name}",
                task_ids=milestone_task_ids,
                status=TaskStatus.PENDING,
            )
            milestones.append(milestone)

    return tasks, milestones


def _create_single_task_from_plan(
    plan: dict,
    acceptance_criteria: list[str],
) -> list[Task]:
    """Create a single task when plan doesn't have explicit tasks.

    Args:
        plan: Implementation plan
        acceptance_criteria: Parsed acceptance criteria

    Returns:
        List with single task
    """
    plan_name = plan.get("plan_name", "Feature Implementation")
    summary = plan.get("summary", "Implement the feature as specified")

    # Gather all files from test_strategy
    test_strategy = plan.get("test_strategy", {})
    unit_tests = test_strategy.get("unit_tests", [])
    integration_tests = test_strategy.get("integration_tests", [])
    test_files = unit_tests + integration_tests

    task = create_task(
        task_id="T1",
        title=plan_name,
        user_story=f"As a user, I want {plan_name.lower()} so that {summary.lower()}",
        acceptance_criteria=acceptance_criteria,
        dependencies=[],
        priority="high",
        milestone_id="M1",
        estimated_complexity=plan.get("estimated_complexity", "medium"),
        files_to_create=[],
        files_to_modify=[],
        test_files=test_files,
    )

    return [task]


def _generate_user_story(description: str, product_md: str) -> str:
    """Generate a user story from task description.

    Args:
        description: Task description
        product_md: PRODUCT.md content for context

    Returns:
        User story in "As a... I want... So that..." format
    """
    # Check if product_md has a user story section
    user_story_pattern = r"(?:user\s*story|as\s+a)[:\s]*\n?(.+?)(?:\n\n|\Z)"
    match = re.search(user_story_pattern, product_md, re.IGNORECASE | re.DOTALL)

    if match:
        story = match.group(1).strip()
        if story.lower().startswith("as a"):
            return story

    # Generate from description
    action = description.lower()
    if action.startswith("create "):
        return f"As a developer, I want to {action} so that the feature works correctly"
    elif action.startswith("add "):
        return f"As a user, I want to have {action[4:]} so that I can use the feature"
    elif action.startswith("implement "):
        return f"As a user, I want {action[10:]} so that the system provides this functionality"
    else:
        return f"As a developer, I want to {action} so that the requirements are met"


def _match_criteria_to_task(description: str, all_criteria: list[str]) -> list[str]:
    """Match acceptance criteria to a specific task.

    Args:
        description: Task description
        all_criteria: All acceptance criteria from PRODUCT.md

    Returns:
        List of criteria relevant to this task
    """
    matched = []
    desc_lower = description.lower()
    desc_words = set(desc_lower.split())

    for criterion in all_criteria:
        criterion_lower = criterion.lower()
        criterion_words = set(criterion_lower.split())

        # Check for word overlap
        overlap = desc_words & criterion_words
        # Remove common words
        common_words = {"the", "a", "an", "is", "are", "be", "to", "and", "or", "of", "in", "on", "for", "with"}
        meaningful_overlap = overlap - common_words

        if len(meaningful_overlap) >= 2:
            matched.append(criterion)
        elif any(word in criterion_lower for word in desc_words if len(word) > 4):
            matched.append(criterion)

    return matched if matched else all_criteria[:3]  # Default to first 3 if no matches


def _generate_test_files(files: list[str], plan: dict) -> list[str]:
    """Generate test file paths for source files.

    Args:
        files: Source files for the task
        plan: Implementation plan with test strategy

    Returns:
        List of test file paths
    """
    test_files = []

    # Get test files from plan's test_strategy
    test_strategy = plan.get("test_strategy", {})
    existing_tests = test_strategy.get("unit_tests", []) + test_strategy.get("integration_tests", [])

    for file_path in files:
        path = Path(file_path)

        # Skip if already a test file
        if "test" in path.name.lower():
            test_files.append(file_path)
            continue

        # Generate test file path based on extension
        ext = path.suffix
        name = path.stem

        if ext in (".py",):
            test_name = f"test_{name}.py"
            test_path = path.parent / test_name
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            test_name = f"{name}.test{ext}"
            test_path = path.parent / test_name
        elif ext in (".go",):
            test_name = f"{name}_test.go"
            test_path = path.parent / test_name
        elif ext in (".rs",):
            test_name = f"{name}_test.rs"
            test_path = path.parent / test_name
        else:
            continue

        # Check if in existing tests
        test_str = str(test_path)
        if test_str in existing_tests or any(test_str.endswith(t) for t in existing_tests):
            test_files.append(test_str)
        else:
            test_files.append(test_str)

    return test_files


def _estimate_priority(description: str, criteria: list[str]) -> str:
    """Estimate task priority based on description and criteria.

    Args:
        description: Task description
        criteria: Matched acceptance criteria

    Returns:
        Priority string (critical, high, medium, low)
    """
    text = (description + " " + " ".join(criteria)).lower()

    for priority, keywords in PRIORITY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return priority

    return "medium"


def _estimate_complexity(description: str, files: list[str]) -> str:
    """Estimate task complexity.

    Args:
        description: Task description
        files: Files involved

    Returns:
        Complexity string (low, medium, high)
    """
    desc_lower = description.lower()

    # Check for complexity indicators
    for complexity, indicators in COMPLEXITY_INDICATORS.items():
        if any(ind in desc_lower for ind in indicators):
            return complexity

    # Estimate based on file count
    if len(files) > 5:
        return "high"
    elif len(files) > 2:
        return "medium"

    return "low"


def _assign_dependencies(tasks: list[Task]) -> list[Task]:
    """Assign dependencies based on file relationships.

    Tasks that modify files created by other tasks depend on those tasks.

    Args:
        tasks: List of tasks

    Returns:
        Tasks with updated dependencies
    """
    # Build file creation map
    file_creators: dict[str, str] = {}
    for task in tasks:
        for file_path in task.get("files_to_create", []):
            file_creators[file_path] = task["id"]

    # Assign dependencies
    for task in tasks:
        existing_deps = set(task.get("dependencies", []))

        for file_path in task.get("files_to_modify", []):
            if file_path in file_creators:
                creator_id = file_creators[file_path]
                if creator_id != task["id"] and creator_id not in existing_deps:
                    existing_deps.add(creator_id)

        task["dependencies"] = list(existing_deps)

    return tasks


def detect_circular_dependencies(tasks: list[Task]) -> list[list[str]]:
    """Detect circular dependencies in tasks using DFS.

    Uses depth-first search to find cycles in the task dependency graph.

    Args:
        tasks: List of tasks with dependencies

    Returns:
        List of cycles found, each cycle is a list of task IDs forming the cycle
    """
    # Build adjacency list (task_id -> list of dependencies)
    graph: dict[str, list[str]] = {}
    for task in tasks:
        task_id = task.get("id", "")
        dependencies = task.get("dependencies", [])
        graph[task_id] = dependencies

    # Track visited nodes and current recursion stack
    visited: set[str] = set()
    rec_stack: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str]) -> None:
        """Depth-first search to detect cycles."""
        if node in rec_stack:
            # Found a cycle - extract the cycle portion from path
            if node in path:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
            return

        if node in visited:
            return

        visited.add(node)
        rec_stack.add(node)

        for dep in graph.get(node, []):
            dfs(dep, path + [node])

        rec_stack.remove(node)

    # Run DFS from each node
    for task_id in graph:
        if task_id not in visited:
            dfs(task_id, [])

    return cycles
