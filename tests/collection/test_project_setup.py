"""Tests for the project_setup module.

Tests the ProjectGuardrailsSetup service that copies collection items
to project directories and generates cursor rules.
"""

import json
import tempfile
from pathlib import Path

import pytest

from orchestrator.collection.models import CollectionItem, CollectionTags, ItemType
from orchestrator.collection.project_setup import ApplyResult, ProjectGuardrailsSetup


class TestProjectGuardrailsSetup:
    """Test suite for ProjectGuardrailsSetup."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def temp_collection_dir(self):
        """Create a temporary collection directory with sample items."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir)

            # Create sample rule
            rules_dir = collection_path / "rules" / "guardrails"
            rules_dir.mkdir(parents=True)
            (rules_dir / "security.md").write_text("# Security Rules\nDon't commit secrets.")

            # Create sample skill
            skills_dir = collection_path / "skills" / "implement"
            skills_dir.mkdir(parents=True)
            skill_dir = skills_dir / "tdd-workflow"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# TDD Workflow\nWrite tests first.")

            yield collection_path

    @pytest.fixture
    def sample_items(self, temp_collection_dir):
        """Create sample collection items for testing."""
        return [
            CollectionItem(
                id="item1",
                name="security-rules",
                item_type=ItemType.RULE,
                category="guardrails",
                file_path=str(temp_collection_dir / "rules/guardrails/security.md"),
                tags=CollectionTags(
                    technology=["python", "typescript"],
                    feature=["security"],
                    priority="high",
                ),
                summary="Security best practices",
                content="# Security Rules\nDon't commit secrets.",
            ),
            CollectionItem(
                id="item2",
                name="tdd-workflow",
                item_type=ItemType.SKILL,
                category="implement",
                file_path=str(temp_collection_dir / "skills/implement/tdd-workflow"),
                tags=CollectionTags(
                    technology=["python"],
                    feature=["testing"],
                    priority="medium",
                ),
                summary="TDD workflow skill",
                content="# TDD Workflow\nWrite tests first.",
            ),
        ]

    @pytest.mark.asyncio
    async def test_apply_guardrails_copies_rules(self, temp_project_dir, sample_items):
        """Test that apply_guardrails copies rule files to project."""
        setup = ProjectGuardrailsSetup()

        result = await setup.apply_guardrails(
            project_path=temp_project_dir,
            items=[sample_items[0]],  # Just the rule
        )

        assert isinstance(result, ApplyResult)
        assert len(result.items_applied) > 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_apply_guardrails_creates_conductor_directory(
        self, temp_project_dir, sample_items
    ):
        """Test that .conductor directory is created."""
        setup = ProjectGuardrailsSetup()

        await setup.apply_guardrails(
            project_path=temp_project_dir,
            items=[sample_items[0]],
        )

        conductor_dir = temp_project_dir / ".conductor"
        assert conductor_dir.exists()

    @pytest.mark.asyncio
    async def test_apply_guardrails_creates_subdirectories(self, temp_project_dir, sample_items):
        """Test that .conductor subdirectories are created."""
        setup = ProjectGuardrailsSetup()

        await setup.apply_guardrails(
            project_path=temp_project_dir,
            items=sample_items,
        )

        # Check subdirectories
        assert (temp_project_dir / ".conductor" / "guardrails").exists()
        assert (temp_project_dir / ".conductor" / "rules").exists()
        assert (temp_project_dir / ".conductor" / "skills").exists()

    @pytest.mark.asyncio
    async def test_apply_guardrails_with_empty_items(self, temp_project_dir):
        """Test that empty items list returns empty result."""
        setup = ProjectGuardrailsSetup()

        result = await setup.apply_guardrails(
            project_path=temp_project_dir,
            items=[],
        )

        assert len(result.items_applied) == 0

    @pytest.mark.asyncio
    async def test_apply_guardrails_handles_missing_files(self, temp_project_dir):
        """Test graceful handling when source file doesn't exist."""
        setup = ProjectGuardrailsSetup()

        missing_item = CollectionItem(
            id="missing",
            name="missing-item",
            item_type=ItemType.RULE,
            category="guardrails",
            file_path="/nonexistent/path/file.md",
            tags=CollectionTags(),
            summary="Missing file",
            content="",
        )

        result = await setup.apply_guardrails(
            project_path=temp_project_dir,
            items=[missing_item],
        )

        # Should handle gracefully - item not applied
        assert len(result.items_applied) == 0

    @pytest.mark.asyncio
    async def test_generate_cursor_rules(self, temp_project_dir):
        """Test that .mdc cursor rules are generated."""
        setup = ProjectGuardrailsSetup()

        rule = CollectionItem(
            id="rule1",
            name="test-rule",
            item_type=ItemType.RULE,
            category="guardrails",
            file_path="/path/to/rule.md",
            tags=CollectionTags(priority="high"),
            summary="Test rule",
            content="# Test Rule\nFollow this rule.",
        )

        created = await setup.generate_cursor_rules(
            project_path=temp_project_dir,
            rules=[rule],
        )

        # Check that cursor directory was created
        cursor_rules_dir = temp_project_dir / ".cursor" / "rules"
        assert cursor_rules_dir.exists()

        # Check file was created
        assert len(created) > 0
        assert any("rule1.mdc" in f for f in created)

    @pytest.mark.asyncio
    async def test_update_agent_files_creates_claude_md(self, temp_project_dir):
        """Test that CLAUDE.md is created with minimal content."""
        setup = ProjectGuardrailsSetup()

        _updated = await setup.update_agent_files(
            project_path=temp_project_dir,
        )

        # Check that CLAUDE.md exists
        claude_file = temp_project_dir / "CLAUDE.md"
        assert claude_file.exists()

        # Check content contains conductor reference
        content = claude_file.read_text()
        assert ".conductor" in content

    @pytest.mark.asyncio
    async def test_update_agent_files_creates_gemini_md(self, temp_project_dir):
        """Test that GEMINI.md is created with minimal content."""
        setup = ProjectGuardrailsSetup()

        _updated = await setup.update_agent_files(
            project_path=temp_project_dir,
        )

        # Check that GEMINI.md exists
        gemini_file = temp_project_dir / "GEMINI.md"
        assert gemini_file.exists()

        # Check content
        content = gemini_file.read_text()
        assert ".conductor" in content

    @pytest.mark.asyncio
    async def test_manifest_is_written(self, temp_project_dir, sample_items):
        """Test that manifest.json is created."""
        setup = ProjectGuardrailsSetup()

        await setup.apply_guardrails(
            project_path=temp_project_dir,
            items=[sample_items[0]],
        )

        manifest_path = temp_project_dir / ".conductor" / "manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert "version" in manifest
        assert "applied_at" in manifest
        assert "items" in manifest


class TestApplyResult:
    """Test the ApplyResult dataclass."""

    def test_result_initialization(self):
        """Test result can be initialized with all fields."""
        result = ApplyResult(
            project_path="/tmp/test",
            items_applied=["item1", "item2"],
            files_created=["file1.md", "file2.md"],
            cursor_rules_created=["rule1.mdc"],
            errors=[],
        )

        assert result.project_path == "/tmp/test"
        assert len(result.items_applied) == 2
        assert len(result.files_created) == 2
        assert len(result.cursor_rules_created) == 1
        assert len(result.errors) == 0

    def test_result_with_errors(self):
        """Test result with errors."""
        result = ApplyResult(
            project_path="/tmp/test",
            items_applied=[],
            files_created=[],
            cursor_rules_created=[],
            errors=["File not found", "Permission denied"],
        )

        assert len(result.items_applied) == 0
        assert len(result.errors) == 2

    def test_result_default_values(self):
        """Test result with minimal initialization."""
        result = ApplyResult(project_path="/tmp/test")

        assert result.project_path == "/tmp/test"
        assert result.items_applied == []
        assert result.files_created == []
        assert result.cursor_rules_created == []
        assert result.errors == []
