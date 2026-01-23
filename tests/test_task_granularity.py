"""Tests for task granularity validation and auto-split.

Tests cover:
1. TaskSizeConfig loading and defaults
2. ComplexityScorer multi-dimensional assessment
3. Task validation using complexity scores
4. Auto-split logic with strategy selection
5. Integration with task_breakdown_node

Run with: uv run pytest tests/test_task_granularity.py -v
"""

import json

import pytest

from orchestrator.langgraph.nodes.task_breakdown import (
    _auto_split_large_task,
    _create_batches_from_groups,
    _determine_split_strategy,
    _distribute_items,
    _group_files_by_directory,
    validate_and_split_tasks,
)
from orchestrator.langgraph.state import create_task
from orchestrator.utils.task_config import (
    DEFAULT_COMPLEXITY_THRESHOLD,
    DEFAULT_MAX_ACCEPTANCE_CRITERIA,
    DEFAULT_MAX_FILES_TO_CREATE,
    DEFAULT_MAX_FILES_TO_MODIFY,
    DEFAULT_MAX_INPUT_TOKENS,
    ComplexityLevel,
    ComplexityScore,
    ComplexityScorer,
    TaskSizeConfig,
    validate_task_complexity,
)

# =============================================================================
# Test TaskSizeConfig
# =============================================================================


class TestTaskSizeConfig:
    """Test TaskSizeConfig loading and defaults."""

    def test_default_values(self):
        """Test default configuration values."""
        config = TaskSizeConfig()

        assert config.max_files_to_create == DEFAULT_MAX_FILES_TO_CREATE
        assert config.max_files_to_modify == DEFAULT_MAX_FILES_TO_MODIFY
        assert config.max_acceptance_criteria == DEFAULT_MAX_ACCEPTANCE_CRITERIA
        assert config.complexity_threshold == DEFAULT_COMPLEXITY_THRESHOLD
        assert config.max_input_tokens == DEFAULT_MAX_INPUT_TOKENS
        assert config.auto_split_enabled is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = TaskSizeConfig(
            max_files_to_create=5,
            max_files_to_modify=10,
            max_acceptance_criteria=8,
            complexity_threshold=7.0,
            auto_split_enabled=False,
        )

        assert config.max_files_to_create == 5
        assert config.max_files_to_modify == 10
        assert config.max_acceptance_criteria == 8
        assert config.complexity_threshold == 7.0
        assert config.auto_split_enabled is False

    def test_invalid_values(self):
        """Test validation of invalid values."""
        with pytest.raises(ValueError):
            TaskSizeConfig(max_files_to_create=0)

        with pytest.raises(ValueError):
            TaskSizeConfig(max_files_to_modify=-1)

        with pytest.raises(ValueError):
            TaskSizeConfig(max_input_tokens=500)  # Below 1000 minimum

        with pytest.raises(ValueError):
            TaskSizeConfig(complexity_threshold=15.0)  # Above 13 maximum

    def test_from_project_config_no_file(self, temp_project_dir):
        """Test loading from non-existent config."""
        config = TaskSizeConfig.from_project_config(temp_project_dir)

        # Should return defaults
        assert config.max_files_to_create == DEFAULT_MAX_FILES_TO_CREATE

    def test_from_project_config_with_file(self, temp_project_dir):
        """Test loading from existing config file."""
        config_data = {
            "task_size_limits": {
                "max_files_to_create": 4,
                "max_files_to_modify": 8,
                "max_criteria_per_task": 6,
                "complexity_threshold": 8.0,
                "auto_split": False,
            }
        }
        config_path = temp_project_dir / ".project-config.json"
        config_path.write_text(json.dumps(config_data))

        config = TaskSizeConfig.from_project_config(temp_project_dir)

        assert config.max_files_to_create == 4
        assert config.max_files_to_modify == 8
        assert config.max_acceptance_criteria == 6
        assert config.complexity_threshold == 8.0
        assert config.auto_split_enabled is False

    def test_from_project_config_partial(self, temp_project_dir):
        """Test loading with partial config."""
        config_data = {
            "task_size_limits": {
                "max_files_to_create": 2,
            }
        }
        config_path = temp_project_dir / ".project-config.json"
        config_path.write_text(json.dumps(config_data))

        config = TaskSizeConfig.from_project_config(temp_project_dir)

        # Specified value used
        assert config.max_files_to_create == 2
        # Defaults for unspecified values
        assert config.max_files_to_modify == DEFAULT_MAX_FILES_TO_MODIFY

    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = TaskSizeConfig(max_files_to_create=5)
        d = config.to_dict()

        assert d["max_files_to_create"] == 5
        assert "max_files_to_modify" in d
        assert "complexity_threshold" in d
        assert "auto_split_enabled" in d


# =============================================================================
# Test ComplexityScore
# =============================================================================


class TestComplexityScore:
    """Test ComplexityScore calculations."""

    def test_total_score(self):
        """Test total score calculation."""
        score = ComplexityScore(
            file_scope=2.5,
            cross_file_deps=1.0,
            semantic_complexity=1.5,
            requirement_uncertainty=0.5,
            token_penalty=0.5,
        )

        assert score.total == 6.0

    def test_complexity_levels(self):
        """Test complexity level thresholds."""
        # LOW: 0-4
        low = ComplexityScore(file_scope=2.0)
        assert low.level == ComplexityLevel.LOW

        # MEDIUM: 5-7
        medium = ComplexityScore(file_scope=3.0, semantic_complexity=2.5)
        assert medium.level == ComplexityLevel.MEDIUM

        # HIGH: 8-10
        high = ComplexityScore(file_scope=4.0, cross_file_deps=2.0, semantic_complexity=2.5)
        assert high.level == ComplexityLevel.HIGH

        # CRITICAL: 11-13
        critical = ComplexityScore(
            file_scope=5.0,
            cross_file_deps=2.0,
            semantic_complexity=3.0,
            requirement_uncertainty=2.0,
        )
        assert critical.level == ComplexityLevel.CRITICAL

    def test_to_dict(self):
        """Test ComplexityScore serialization."""
        score = ComplexityScore(file_scope=2.5, semantic_complexity=1.5)
        d = score.to_dict()

        assert d["file_scope"] == 2.5
        assert d["semantic_complexity"] == 1.5
        assert d["total"] == 4.0
        assert d["level"] == "low"


# =============================================================================
# Test ComplexityScorer
# =============================================================================


class TestComplexityScorer:
    """Test ComplexityScorer multi-dimensional assessment."""

    def test_simple_task_low_score(self):
        """Test scoring a simple task."""
        config = TaskSizeConfig()
        scorer = ComplexityScorer(config)

        task = {
            "id": "T1",
            "title": "Add helper function",
            "user_story": "As a developer, I want a helper",
            "acceptance_criteria": ["Function exists"],
            "files_to_create": ["src/helper.py"],
            "files_to_modify": [],
        }

        score = scorer.score_task(task)

        assert score.total < 5  # Should be LOW complexity
        assert score.level == ComplexityLevel.LOW
        assert score.file_scope <= 1.0  # 1 file * 0.5

    def test_complex_task_high_score(self):
        """Test scoring a complex task."""
        config = TaskSizeConfig()
        scorer = ComplexityScorer(config)

        task = {
            "id": "T1",
            "title": "Implement distributed caching algorithm",
            "user_story": "As a user, I want performance optimization",
            "acceptance_criteria": [
                "Cache is thread-safe",
                "Handles concurrent access",
                "Performance benchmark passes",
            ],
            "files_to_create": [
                "src/cache/manager.py",
                "src/cache/storage.py",
                "src/cache/sync.py",
            ],
            "files_to_modify": [
                "src/models/data.py",
                "src/services/handler.py",
            ],
        }

        score = scorer.score_task(task)

        # Should have high semantic complexity due to keywords
        assert score.semantic_complexity >= 2.0
        # Should have moderate file scope
        assert score.file_scope >= 2.0
        # Total should be MEDIUM or HIGH
        assert score.total >= 5

    def test_file_scope_scoring(self):
        """Test file scope scoring (0-5 points)."""
        config = TaskSizeConfig()
        scorer = ComplexityScorer(config)

        # 2 files = 1.0 points
        task_small = {"files_to_create": ["a.py"], "files_to_modify": ["b.py"]}
        assert scorer.score_task(task_small).file_scope == 1.0

        # 10 files = 5.0 points (capped)
        task_large = {"files_to_create": list(f"{i}.py" for i in range(10))}
        assert scorer.score_task(task_large).file_scope == 5.0

    def test_cross_file_deps_scoring(self):
        """Test cross-file dependency scoring."""
        config = TaskSizeConfig()
        scorer = ComplexityScorer(config)

        # Single directory = low coupling
        task_single_dir = {
            "files_to_create": ["src/a.py", "src/b.py"],
            "files_to_modify": [],
        }
        score_single = scorer.score_task(task_single_dir)
        assert score_single.cross_file_deps <= 1.0

        # Multiple directories = higher coupling
        task_multi_dir = {
            "files_to_create": ["models/a.py", "views/b.py", "services/c.py"],
            "files_to_modify": ["utils/d.py"],
        }
        score_multi = scorer.score_task(task_multi_dir)
        assert score_multi.cross_file_deps >= 1.0

    def test_semantic_complexity_keywords(self):
        """Test semantic complexity based on keywords."""
        config = TaskSizeConfig()
        scorer = ComplexityScorer(config)

        # High complexity keywords
        high_complexity = {
            "title": "Implement concurrent algorithm with async optimization",
            "user_story": "",
            "acceptance_criteria": [],
        }
        score_high = scorer.score_task(high_complexity)
        assert score_high.semantic_complexity >= 2.0

        # Medium complexity keywords
        medium_complexity = {
            "title": "Create database query handler",
            "user_story": "",
            "acceptance_criteria": [],
        }
        score_medium = scorer.score_task(medium_complexity)
        assert score_medium.semantic_complexity >= 0.5

    def test_uncertainty_scoring(self):
        """Test requirement uncertainty scoring."""
        config = TaskSizeConfig()
        scorer = ComplexityScorer(config)

        # Uncertain requirements
        uncertain = {
            "title": "Implement feature",
            "user_story": "Should possibly work",
            "acceptance_criteria": [
                "Might need configuration",
                "Consider optional parameters",
                "TBD based on feedback",
            ],
        }
        score = scorer.score_task(uncertain)
        assert score.requirement_uncertainty >= 1.0

    def test_token_penalty(self):
        """Test token budget penalty."""
        config = TaskSizeConfig(max_input_tokens=3000)
        scorer = ComplexityScorer(config)

        # Large task exceeding token budget
        large_task = {
            "title": "Large refactoring",
            "user_story": "Refactor everything",
            "acceptance_criteria": ["Done"],
            "files_to_modify": list(f"src/{i}.py" for i in range(20)),  # Many files
        }
        score = scorer.score_task(large_task)
        assert score.token_penalty > 0

    def test_estimate_time(self):
        """Test time estimation."""
        config = TaskSizeConfig()
        scorer = ComplexityScorer(config)

        task = {
            "files_to_create": ["a.py", "b.py"],
            "files_to_modify": ["c.py"],
        }
        time = scorer.estimate_time_minutes(task)

        # Should estimate based on files and complexity
        assert time >= 1.0


# =============================================================================
# Test Task Validation
# =============================================================================


class TestTaskValidation:
    """Test task granularity validation using complexity scoring."""

    def test_valid_task_low_complexity(self):
        """Test validation of simple task within complexity threshold."""
        config = TaskSizeConfig(complexity_threshold=5.0)
        task = create_task(
            task_id="T1",
            title="Create helper module",
            user_story="As a dev, I want a helper",
            acceptance_criteria=["Function works"],
            dependencies=[],
            files_to_create=["src/helper.py"],
            files_to_modify=[],
        )

        result = validate_task_complexity(task, config)

        assert result.is_valid is True
        assert result.should_split is False
        assert result.complexity_score.level == ComplexityLevel.LOW

    def test_invalid_task_high_complexity(self):
        """Test validation of complex task exceeding threshold."""
        config = TaskSizeConfig(complexity_threshold=5.0)
        task = create_task(
            task_id="T1",
            title="Implement distributed caching with async optimization",
            user_story="As a dev, I want performance",
            acceptance_criteria=[
                "Cache works",
                "Thread-safe",
                "Handles concurrent access",
            ],
            dependencies=[],
            files_to_create=[
                "src/cache/manager.py",
                "src/cache/storage.py",
                "src/cache/sync.py",
                "src/cache/config.py",
            ],
            files_to_modify=[
                "src/models/data.py",
                "src/services/handler.py",
            ],
        )

        result = validate_task_complexity(task, config)

        assert result.should_split is True
        assert result.complexity_score.total > config.complexity_threshold

    def test_soft_limit_warnings(self):
        """Test that file limits generate warnings but don't force splits."""
        config = TaskSizeConfig(
            max_files_to_create=2,  # Soft limit
            complexity_threshold=10.0,  # High threshold
        )
        task = create_task(
            task_id="T1",
            title="Simple task",
            user_story="Story",
            acceptance_criteria=["Done"],
            dependencies=[],
            files_to_create=["a.py", "b.py", "c.py"],  # Exceeds soft limit
            files_to_modify=[],
        )

        result = validate_task_complexity(task, config)

        # Should NOT split due to high threshold
        assert result.should_split is False
        # But should have warning
        assert len(result.warnings) > 0
        assert "files_to_create" in result.warnings[0]

    def test_validation_result_serialization(self):
        """Test TaskValidationResult serialization."""
        config = TaskSizeConfig()
        task = create_task(
            task_id="T1",
            title="Task",
            user_story="Story",
            acceptance_criteria=["C1"],
            dependencies=[],
        )

        result = validate_task_complexity(task, config)
        d = result.to_dict()

        assert "should_split" in d
        assert "complexity_score" in d
        assert "estimated_tokens" in d
        assert "warnings" in d
        assert "recommendation" in d


# =============================================================================
# Test Split Strategy Selection
# =============================================================================


class TestSplitStrategySelection:
    """Test automatic split strategy selection."""

    def test_files_strategy_for_high_file_scope(self):
        """Test files strategy when file scope is dominant."""
        score = ComplexityScore(
            file_scope=4.0,
            cross_file_deps=0.5,
            semantic_complexity=1.0,
        )
        task = {
            "files_to_create": ["a.py", "b.py", "c.py", "d.py", "e.py"],
            "files_to_modify": [],
        }

        strategy = _determine_split_strategy(score, task)

        assert strategy == "files"

    def test_layers_strategy_for_high_cross_deps(self):
        """Test layers strategy when cross-file deps are dominant."""
        score = ComplexityScore(
            file_scope=1.0,
            cross_file_deps=2.0,
            semantic_complexity=0.5,
        )
        task = {
            "files_to_create": ["models/a.py", "views/b.py"],
            "files_to_modify": [],
        }

        strategy = _determine_split_strategy(score, task)

        assert strategy == "layers"

    def test_criteria_strategy_for_high_semantic(self):
        """Test criteria strategy when semantic complexity is high."""
        score = ComplexityScore(
            file_scope=1.0,
            cross_file_deps=0.5,
            semantic_complexity=3.0,
        )
        task = {
            "files_to_create": ["a.py"],
            "files_to_modify": [],
        }

        strategy = _determine_split_strategy(score, task)

        assert strategy == "criteria"


# =============================================================================
# Test Auto-Split Helpers
# =============================================================================


class TestAutoSplitHelpers:
    """Test helper functions for auto-split."""

    def test_group_files_by_directory(self):
        """Test grouping files by their directory."""
        files = [
            "src/models/user.py",
            "src/models/product.py",
            "src/views/home.py",
            "tests/test_user.py",
        ]

        groups = _group_files_by_directory(files)

        assert len(groups) == 3
        assert len(groups["src/models"]) == 2
        assert len(groups["src/views"]) == 1
        assert len(groups["tests"]) == 1

    def test_create_batches_from_groups(self):
        """Test creating batches from grouped files."""
        groups = {
            "src/models": ["a.py", "b.py", "c.py"],
            "src/views": ["d.py"],
        }

        batches = _create_batches_from_groups(groups, max_per_batch=2)

        assert len(batches) == 2
        assert len(batches[0]) == 2
        assert len(batches[1]) == 2

    def test_create_batches_empty(self):
        """Test creating batches from empty groups."""
        batches = _create_batches_from_groups({}, max_per_batch=3)
        assert len(batches) == 0

    def test_distribute_items(self):
        """Test distributing items across batches."""
        items = ["A", "B", "C", "D", "E"]

        distributed = _distribute_items(items, num_batches=3)

        assert len(distributed) == 3
        # Round-robin distribution: A,D in first, B,E in second, C in third
        assert len(distributed[0]) == 2
        assert len(distributed[1]) == 2
        assert len(distributed[2]) == 1

    def test_distribute_items_empty(self):
        """Test distributing empty list."""
        distributed = _distribute_items([], num_batches=3)
        assert len(distributed) == 3
        assert all(len(batch) == 0 for batch in distributed)


# =============================================================================
# Test Auto-Split Logic
# =============================================================================


class TestAutoSplit:
    """Test auto-split functionality."""

    def test_split_reduces_complexity(self):
        """Test that splitting reduces complexity of resulting tasks."""
        config = TaskSizeConfig(complexity_threshold=5.0)
        task = create_task(
            task_id="T1",
            title="Create distributed caching system",
            user_story="As a dev...",
            acceptance_criteria=["C1", "C2", "C3", "C4"],
            dependencies=[],
            priority="high",
            milestone_id="M1",
            files_to_create=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            files_to_modify=[],
        )

        split_tasks = _auto_split_large_task(task, config, base_task_num=1)

        assert len(split_tasks) >= 2

        # Each split task should have fewer files
        for split_task in split_tasks:
            files_count = len(split_task.get("files_to_create", [])) + len(
                split_task.get("files_to_modify", [])
            )
            assert files_count < 6

    def test_split_chains_dependencies(self):
        """Test that split tasks are chained with dependencies."""
        config = TaskSizeConfig(complexity_threshold=5.0)
        task = create_task(
            task_id="T1",
            title="Create many files",
            user_story="As a dev...",
            acceptance_criteria=["C1", "C2"],
            dependencies=[],
            priority="high",
            milestone_id="M1",
            files_to_create=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            files_to_modify=[],
        )

        split_tasks = _auto_split_large_task(task, config, base_task_num=1)

        assert len(split_tasks) >= 2
        # First split task
        assert split_tasks[0]["id"] == "T1-a"
        # Second split task should depend on first
        assert "T1-a" in split_tasks[1].get("dependencies", [])
        # Priority and milestone preserved
        assert split_tasks[0]["priority"] == "high"
        assert split_tasks[0]["milestone_id"] == "M1"

    def test_split_distributes_criteria(self):
        """Test that criteria are distributed across split tasks."""
        config = TaskSizeConfig(complexity_threshold=3.0)
        task = create_task(
            task_id="T1",
            title="Task",
            user_story="Story",
            acceptance_criteria=["C1", "C2", "C3", "C4"],
            dependencies=[],
            files_to_create=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            files_to_modify=[],
        )

        split_tasks = _auto_split_large_task(task, config, base_task_num=1)

        # Criteria should be distributed
        total_criteria = sum(len(t.get("acceptance_criteria", [])) for t in split_tasks)
        assert total_criteria == 4

    def test_split_preserves_original_dependencies(self):
        """Test that original dependencies are preserved in first split task."""
        config = TaskSizeConfig(complexity_threshold=3.0)
        task = create_task(
            task_id="T2",
            title="Task",
            user_story="Story",
            acceptance_criteria=["C1"],
            dependencies=["T1"],  # Original dependency
            files_to_create=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            files_to_modify=[],
        )

        split_tasks = _auto_split_large_task(task, config, base_task_num=2)

        # First split task should have original dependency
        assert "T1" in split_tasks[0].get("dependencies", [])
        # Second split task should depend on first split (not original)
        assert "T2-a" in split_tasks[1].get("dependencies", [])

    def test_split_generates_test_files(self):
        """Test that split tasks get appropriate test files."""
        config = TaskSizeConfig(complexity_threshold=3.0)
        task = create_task(
            task_id="T1",
            title="Task",
            user_story="Story",
            acceptance_criteria=["C1"],
            dependencies=[],
            files_to_create=[
                "src/module.py",
                "src/helper.py",
                "src/utils.py",
                "src/config.py",
                "src/core.py",
            ],
            files_to_modify=[],
        )

        split_tasks = _auto_split_large_task(task, config, base_task_num=1)

        # Each split task with files should have test files
        for split_task in split_tasks:
            if split_task.get("files_to_create"):
                assert len(split_task.get("test_files", [])) > 0


# =============================================================================
# Test validate_and_split_tasks Integration
# =============================================================================


class TestValidateAndSplitTasks:
    """Test the main validate_and_split_tasks function."""

    def test_no_split_needed(self, temp_project_dir):
        """Test when no tasks need splitting."""
        tasks = [
            create_task(
                task_id="T1",
                title="Small task",
                user_story="Story",
                acceptance_criteria=["C1"],
                dependencies=[],
                files_to_create=["a.py"],
                files_to_modify=[],
            ),
        ]

        result = validate_and_split_tasks(tasks, temp_project_dir)

        assert len(result) == 1
        assert result[0]["id"] == "T1"

    def test_split_complex_task(self, temp_project_dir):
        """Test splitting a task that exceeds complexity threshold."""
        # Configure lower threshold for testing
        config_data = {
            "task_size_limits": {
                "complexity_threshold": 3.0,
            }
        }
        config_path = temp_project_dir / ".project-config.json"
        config_path.write_text(json.dumps(config_data))

        tasks = [
            create_task(
                task_id="T1",
                title="Complex distributed system with async optimization",
                user_story="Story",
                acceptance_criteria=["C1", "C2", "C3"],
                dependencies=[],
                files_to_create=[
                    "a.py",
                    "b.py",
                    "c.py",
                    "d.py",
                    "e.py",
                    "f.py",
                    "g.py",
                    "h.py",
                ],
                files_to_modify=[],
            ),
        ]

        result = validate_and_split_tasks(tasks, temp_project_dir)

        assert len(result) > 1
        assert result[0]["id"] == "T1-a"

    def test_mixed_tasks(self, temp_project_dir):
        """Test with mix of valid and complex tasks."""
        config_data = {
            "task_size_limits": {
                "complexity_threshold": 4.0,
            }
        }
        config_path = temp_project_dir / ".project-config.json"
        config_path.write_text(json.dumps(config_data))

        tasks = [
            create_task(
                task_id="T1",
                title="Simple task",
                user_story="Story",
                acceptance_criteria=["C1"],
                dependencies=[],
                files_to_create=["a.py"],
                files_to_modify=[],
            ),
            create_task(
                task_id="T2",
                title="Complex algorithm implementation",
                user_story="Story",
                acceptance_criteria=["C1", "C2", "C3"],
                dependencies=["T1"],
                files_to_create=[
                    "b.py",
                    "c.py",
                    "d.py",
                    "e.py",
                    "f.py",
                    "g.py",
                    "h.py",
                    "i.py",
                ],
                files_to_modify=[],
            ),
        ]

        result = validate_and_split_tasks(tasks, temp_project_dir)

        # T1 stays, T2 splits
        assert len(result) >= 3
        assert result[0]["id"] == "T1"
        assert "T2-" in result[1]["id"]

    def test_auto_split_disabled(self, temp_project_dir):
        """Test when auto_split is disabled via config."""
        config_data = {
            "task_size_limits": {
                "auto_split": False,
            }
        }
        config_path = temp_project_dir / ".project-config.json"
        config_path.write_text(json.dumps(config_data))

        tasks = [
            create_task(
                task_id="T1",
                title="Complex distributed algorithm with optimization",
                user_story="Story",
                acceptance_criteria=["C1"],
                dependencies=[],
                files_to_create=[
                    "a.py",
                    "b.py",
                    "c.py",
                    "d.py",
                    "e.py",
                    "f.py",
                    "g.py",
                    "h.py",
                    "i.py",
                    "j.py",
                ],
                files_to_modify=[],
            ),
        ]

        result = validate_and_split_tasks(tasks, temp_project_dir)

        # Should not split when disabled
        assert len(result) == 1
        assert result[0]["id"] == "T1"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
