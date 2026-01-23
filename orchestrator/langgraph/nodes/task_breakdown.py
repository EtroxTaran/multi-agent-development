"""Task breakdown node.

Parses PRODUCT.md acceptance criteria into individual tasks
with dependencies, priorities, and milestones for incremental execution.

Task granularity is enforced via multi-dimensional complexity assessment:
- Complexity score (0-13 scale) as primary decision factor
- File scope, cross-file dependencies, semantic complexity
- Token budget and time estimates
- File limits as soft guidance (warnings, not hard failures)

Research shows file counts alone are insufficient - this module implements
the "Complexity Triangle" principle where tasks must satisfy multiple
constraints simultaneously.
"""

import json
import logging
import re
from collections import defaultdict
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
from ..integrations.board_sync import sync_board
from ...utils.task_config import (
    TaskSizeConfig,
    TaskValidationResult,
    ComplexityScorer,
    ComplexityScore,
    ComplexityLevel,
    validate_task_complexity,
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

    # Validate and auto-split large tasks
    original_count = len(tasks)
    tasks = validate_and_split_tasks(tasks, project_dir)
    if len(tasks) != original_count:
        # Update milestone task_ids after splitting
        for milestone in milestones:
            new_task_ids = []
            for task_id in milestone.task_ids:
                # Find all tasks that start with the original ID (including splits)
                for task in tasks:
                    if task["id"] == task_id or task["id"].startswith(f"{task_id}-"):
                        new_task_ids.append(task["id"])
            milestone.task_ids = new_task_ids

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

    # Save tasks to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    tasks_output = {
        "tasks": [dict(t) for t in tasks],
        "milestones": [dict(m) for m in milestones],
        "created_at": datetime.now().isoformat(),
        "source": "task_breakdown_node",
    }
    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save(phase=1, output_type="task_breakdown", content=tasks_output))

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

    # Sync to Kanban board
    try:
        sync_state = dict(state)
        sync_state["tasks"] = tasks
        sync_board(sync_state)
    except Exception as e:
        logger.warning(f"Failed to sync board in task breakdown: {e}")

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


def _validate_task_granularity(
    task: Task,
    config: TaskSizeConfig,
) -> TaskValidationResult:
    """Validate task using multi-dimensional complexity assessment.

    Uses the Complexity Triangle principle:
    - File scope (0-5 points)
    - Cross-file dependencies (0-2 points)
    - Semantic complexity (0-3 points)
    - Requirement uncertainty (0-2 points)
    - Token penalty (0-1 point)

    Total: 0-13 scale, split threshold configurable (default: 5)

    Args:
        task: Task to validate
        config: Task size configuration with complexity threshold

    Returns:
        TaskValidationResult with complexity breakdown and split decision
    """
    return validate_task_complexity(task, config)


def _group_files_by_directory(files: list[str]) -> dict[str, list[str]]:
    """Group files by their parent directory for intelligent splitting.

    Args:
        files: List of file paths

    Returns:
        Dictionary mapping directory paths to files in that directory
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for file_path in files:
        parent = str(Path(file_path).parent)
        groups[parent].append(file_path)
    return dict(groups)


def _auto_split_large_task(
    task: Task,
    config: TaskSizeConfig,
    base_task_num: int,
    validation_result: Optional[TaskValidationResult] = None,
) -> list[Task]:
    """Automatically split a complex task into smaller tasks.

    Uses complexity-aware splitting:
    1. Analyzes which complexity factors are highest
    2. Splits along the most impactful dimension first
    3. Groups related files by directory/semantic boundary
    4. Distributes acceptance criteria to maintain coherence
    5. Chains dependencies: T1-a -> T1-b -> T1-c

    Args:
        task: Task to split
        config: Task size configuration
        base_task_num: Base number for generating sub-task IDs
        validation_result: Optional pre-computed validation result

    Returns:
        List of smaller tasks with lower complexity scores
    """
    original_id = task.get("id", f"T{base_task_num}")
    files_to_create = task.get("files_to_create", [])
    files_to_modify = task.get("files_to_modify", [])
    acceptance_criteria = task.get("acceptance_criteria", [])
    priority = task.get("priority", "medium")
    milestone_id = task.get("milestone_id")

    # Get complexity breakdown to inform splitting strategy
    if validation_result is None:
        validation_result = _validate_task_granularity(task, config)

    complexity = validation_result.complexity_score
    split_tasks: list[Task] = []

    # Determine split strategy based on highest complexity component
    # This creates smarter splits that address the actual complexity
    split_strategy = _determine_split_strategy(complexity, task)

    if split_strategy == "files":
        # File-based split: group by directory, reduce file scope
        split_tasks = _split_by_files(
            task, config, original_id, files_to_create, files_to_modify,
            acceptance_criteria, priority, milestone_id
        )
    elif split_strategy == "layers":
        # Architectural split: separate by layer to reduce cross-file deps
        split_tasks = _split_by_layers(
            task, config, original_id, files_to_create, files_to_modify,
            acceptance_criteria, priority, milestone_id
        )
    elif split_strategy == "criteria":
        # Criteria split: separate acceptance criteria to reduce scope
        split_tasks = _split_by_criteria(
            task, config, original_id, files_to_create, files_to_modify,
            acceptance_criteria, priority, milestone_id
        )
    else:
        # Default: balanced split by files
        split_tasks = _split_by_files(
            task, config, original_id, files_to_create, files_to_modify,
            acceptance_criteria, priority, milestone_id
        )

    # Verify splits actually reduced complexity
    if split_tasks:
        for split_task in split_tasks:
            split_validation = _validate_task_granularity(split_task, config)
            if split_validation.should_split:
                logger.warning(
                    f"Split task {split_task.get('id')} still has high complexity "
                    f"({split_validation.complexity_score.total:.1f}), may need further splitting"
                )

    logger.info(
        f"Split task {original_id} into {len(split_tasks)} sub-tasks using {split_strategy} strategy: "
        f"{[t.get('id') for t in split_tasks]}"
    )

    return split_tasks


def _determine_split_strategy(
    complexity: ComplexityScore,
    task: Task,
) -> str:
    """Determine the best split strategy based on complexity breakdown.

    Args:
        complexity: Complexity score breakdown
        task: Original task

    Returns:
        Strategy name: "files", "layers", "criteria", or "balanced"
    """
    # Find the dominant complexity factor
    factors = [
        ("files", complexity.file_scope),
        ("layers", complexity.cross_file_deps),
        ("semantic", complexity.semantic_complexity),
        ("uncertainty", complexity.requirement_uncertainty),
    ]

    # Sort by contribution (descending)
    factors.sort(key=lambda x: x[1], reverse=True)
    dominant = factors[0][0]

    # Map to split strategy
    if dominant == "files" and complexity.file_scope >= 2.5:
        return "files"
    elif dominant == "layers" and complexity.cross_file_deps >= 1.5:
        return "layers"
    elif dominant in ("semantic", "uncertainty"):
        # High semantic complexity or uncertainty: split by criteria
        # to create more focused, clearer tasks
        return "criteria"

    # Default to files if no clear dominant factor
    files_to_create = task.get("files_to_create", [])
    files_to_modify = task.get("files_to_modify", [])
    if len(files_to_create) + len(files_to_modify) > 4:
        return "files"

    return "balanced"


def _split_by_files(
    task: Task,
    config: TaskSizeConfig,
    original_id: str,
    files_to_create: list[str],
    files_to_modify: list[str],
    acceptance_criteria: list[str],
    priority: str,
    milestone_id: Optional[str],
) -> list[Task]:
    """Split task by grouping files by directory.

    Keeps related files together to maintain semantic coherence.
    """
    # Group files by directory
    create_groups = _group_files_by_directory(files_to_create)
    modify_groups = _group_files_by_directory(files_to_modify)

    # Target ~3-4 files per split task for optimal complexity
    target_files_per_task = 4
    create_batches = _create_batches_from_groups(create_groups, target_files_per_task)
    modify_batches = _create_batches_from_groups(modify_groups, target_files_per_task)

    # Determine number of split tasks
    max_batches = max(len(create_batches), len(modify_batches), 1)

    # Distribute acceptance criteria
    criteria_per_task = _distribute_items(acceptance_criteria, max_batches)

    return _create_split_tasks(
        task, original_id, create_batches, modify_batches,
        criteria_per_task, priority, milestone_id
    )


def _split_by_layers(
    task: Task,
    config: TaskSizeConfig,
    original_id: str,
    files_to_create: list[str],
    files_to_modify: list[str],
    acceptance_criteria: list[str],
    priority: str,
    milestone_id: Optional[str],
) -> list[Task]:
    """Split task by architectural layer to reduce cross-file dependencies.

    Separates data layer, business layer, and presentation layer.
    """
    layer_keywords = {
        "data": ["models", "repositories", "entities", "schemas", "db"],
        "business": ["services", "core", "domain", "logic", "handlers"],
        "presentation": ["views", "controllers", "api", "routes", "endpoints"],
        "infrastructure": ["utils", "config", "helpers", "common"],
    }

    def classify_file(filepath: str) -> str:
        """Classify file into architectural layer."""
        f_lower = filepath.lower()
        for layer, keywords in layer_keywords.items():
            if any(kw in f_lower for kw in keywords):
                return layer
        return "other"

    # Group all files by layer
    all_files = files_to_create + files_to_modify
    layer_files: dict[str, tuple[list[str], list[str]]] = defaultdict(lambda: ([], []))

    for f in files_to_create:
        layer = classify_file(f)
        layer_files[layer][0].append(f)

    for f in files_to_modify:
        layer = classify_file(f)
        layer_files[layer][1].append(f)

    # Create batches per layer
    create_batches = []
    modify_batches = []

    for layer in ["data", "business", "presentation", "infrastructure", "other"]:
        if layer in layer_files:
            creates, modifies = layer_files[layer]
            if creates:
                create_batches.append(creates)
            if modifies:
                modify_batches.append(modifies)

    # Ensure at least one batch
    if not create_batches and not modify_batches:
        create_batches = [files_to_create] if files_to_create else []
        modify_batches = [files_to_modify] if files_to_modify else []

    max_batches = max(len(create_batches), len(modify_batches), 1)
    criteria_per_task = _distribute_items(acceptance_criteria, max_batches)

    return _create_split_tasks(
        task, original_id, create_batches, modify_batches,
        criteria_per_task, priority, milestone_id
    )


def _split_by_criteria(
    task: Task,
    config: TaskSizeConfig,
    original_id: str,
    files_to_create: list[str],
    files_to_modify: list[str],
    acceptance_criteria: list[str],
    priority: str,
    milestone_id: Optional[str],
) -> list[Task]:
    """Split task by acceptance criteria to create focused sub-tasks.

    Each sub-task gets a subset of criteria and relevant files.
    Good for high semantic complexity or unclear requirements.
    """
    # Target 2-3 criteria per task for clarity
    target_criteria = 3
    num_splits = max(1, (len(acceptance_criteria) + target_criteria - 1) // target_criteria)

    criteria_batches = _distribute_items(acceptance_criteria, num_splits)

    # Distribute files evenly (can't always match criteria to files)
    create_batches = _distribute_items(files_to_create, num_splits)
    modify_batches = _distribute_items(files_to_modify, num_splits)

    return _create_split_tasks(
        task, original_id, create_batches, modify_batches,
        criteria_batches, priority, milestone_id
    )


def _create_split_tasks(
    original_task: Task,
    original_id: str,
    create_batches: list[list[str]],
    modify_batches: list[list[str]],
    criteria_batches: list[list[str]],
    priority: str,
    milestone_id: Optional[str],
) -> list[Task]:
    """Create split task instances from batches.

    Chains dependencies between splits and preserves original dependencies.
    """
    split_tasks: list[Task] = []
    previous_task_id: Optional[str] = None
    max_batches = max(len(create_batches), len(modify_batches), len(criteria_batches), 1)

    for i in range(max_batches):
        sub_task_id = f"{original_id}-{chr(ord('a') + i)}"

        task_files_to_create = create_batches[i] if i < len(create_batches) else []
        task_files_to_modify = modify_batches[i] if i < len(modify_batches) else []
        task_criteria = criteria_batches[i] if i < len(criteria_batches) else []

        # Generate test files
        all_files = task_files_to_create + task_files_to_modify
        test_files = _generate_test_files_for_batch(all_files)

        # Chain dependencies
        dependencies = []
        if previous_task_id:
            dependencies.append(previous_task_id)
        if i == 0:
            original_deps = original_task.get("dependencies", [])
            dependencies.extend(original_deps)

        # Create descriptive title
        if task_files_to_create or task_files_to_modify:
            focus_files = (task_files_to_create + task_files_to_modify)[:2]
            focus_str = ", ".join(Path(f).name for f in focus_files)
            sub_title = f"{original_task.get('title', 'Task')[:50]} ({focus_str})"
        else:
            sub_title = f"{original_task.get('title', 'Task')[:60]} (part {i + 1})"

        sub_task = create_task(
            task_id=sub_task_id,
            title=sub_title[:80],
            user_story=original_task.get("user_story", ""),
            acceptance_criteria=task_criteria,
            dependencies=dependencies,
            priority=priority,
            milestone_id=milestone_id,
            estimated_complexity=_recalculate_complexity(
                task_files_to_create, task_files_to_modify
            ),
            files_to_create=task_files_to_create,
            files_to_modify=task_files_to_modify,
            test_files=test_files,
        )

        split_tasks.append(sub_task)
        previous_task_id = sub_task_id

    return split_tasks


def _create_batches_from_groups(
    groups: dict[str, list[str]],
    max_per_batch: int,
) -> list[list[str]]:
    """Create batches from grouped files, respecting max limit.

    Tries to keep files from the same directory together.

    Args:
        groups: Dictionary mapping directory to files
        max_per_batch: Maximum files per batch

    Returns:
        List of file batches
    """
    if not groups:
        return []

    batches: list[list[str]] = []
    current_batch: list[str] = []

    for _dir, files in sorted(groups.items()):
        for file_path in files:
            if len(current_batch) >= max_per_batch:
                batches.append(current_batch)
                current_batch = []
            current_batch.append(file_path)

    if current_batch:
        batches.append(current_batch)

    return batches


def _distribute_items(items: list[str], num_batches: int) -> list[list[str]]:
    """Distribute items evenly across batches.

    Args:
        items: Items to distribute
        num_batches: Number of batches

    Returns:
        List of item batches
    """
    if not items or num_batches < 1:
        return [[]] * num_batches if num_batches > 0 else []

    batches: list[list[str]] = [[] for _ in range(num_batches)]
    for i, item in enumerate(items):
        batches[i % num_batches].append(item)

    return batches


def _generate_test_files_for_batch(files: list[str]) -> list[str]:
    """Generate test file paths for a batch of source files.

    Args:
        files: Source files

    Returns:
        List of test file paths
    """
    test_files = []
    for file_path in files:
        path = Path(file_path)
        if "test" in path.name.lower():
            continue

        ext = path.suffix
        name = path.stem

        if ext in (".py",):
            test_files.append(str(path.parent / f"test_{name}.py"))
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            test_files.append(str(path.parent / f"{name}.test{ext}"))
        elif ext in (".go",):
            test_files.append(str(path.parent / f"{name}_test.go"))
        elif ext in (".rs",):
            test_files.append(str(path.parent / f"{name}_test.rs"))

    return test_files


def _recalculate_complexity(
    files_to_create: list[str],
    files_to_modify: list[str],
) -> str:
    """Recalculate complexity based on file counts.

    Args:
        files_to_create: Files to create
        files_to_modify: Files to modify

    Returns:
        Complexity string
    """
    total = len(files_to_create) + len(files_to_modify)
    if total > 5:
        return "high"
    elif total > 2:
        return "medium"
    return "low"


def validate_and_split_tasks(
    tasks: list[Task],
    project_dir: Path,
) -> list[Task]:
    """Validate all tasks and split any that exceed limits.

    This is the main entry point for task granularity enforcement.
    Called after initial task extraction.

    Args:
        tasks: List of tasks to validate
        project_dir: Project directory for loading config

    Returns:
        List of tasks with large tasks split
    """
    config = TaskSizeConfig.from_project_config(project_dir)

    if not config.auto_split_enabled:
        logger.info("Auto-split disabled, skipping task validation")
        return tasks

    result_tasks: list[Task] = []
    task_counter = len(tasks) + 1  # For generating new task IDs

    for task in tasks:
        validation = _validate_task_granularity(task, config)

        if validation.is_valid:
            result_tasks.append(task)
        else:
            logger.warning(validation.recommendation)
            split_tasks = _auto_split_large_task(task, config, task_counter)
            result_tasks.extend(split_tasks)
            task_counter += len(split_tasks)

    logger.info(
        f"Task validation complete: {len(tasks)} -> {len(result_tasks)} tasks"
    )

    return result_tasks


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
