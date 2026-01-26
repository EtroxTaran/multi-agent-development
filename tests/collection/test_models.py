"""Tests for collection models."""

from pathlib import Path

from orchestrator.collection.models import (
    CollectionItem,
    CollectionTags,
    CopyResult,
    GapItem,
    ItemType,
    Priority,
    ProjectRequirements,
    SyncResult,
)


class TestCollectionTags:
    """Tests for CollectionTags model."""

    def test_default_values(self):
        """Test default tag values."""
        tags = CollectionTags()
        assert tags.technology == []
        assert tags.feature == []
        assert tags.priority == Priority.MEDIUM.value

    def test_to_dict(self):
        """Test conversion to dictionary."""
        tags = CollectionTags(
            technology=["python", "fastapi"],
            feature=["api", "auth"],
            priority="high",
        )
        result = tags.to_dict()

        assert result["technology"] == ["python", "fastapi"]
        assert result["feature"] == ["api", "auth"]
        assert result["priority"] == "high"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "technology": ["typescript", "react"],
            "feature": ["frontend", "ui"],
            "priority": "critical",
        }
        tags = CollectionTags.from_dict(data)

        assert tags.technology == ["typescript", "react"]
        assert tags.feature == ["frontend", "ui"]
        assert tags.priority == "critical"

    def test_from_dict_with_defaults(self):
        """Test creation from empty dictionary uses defaults."""
        tags = CollectionTags.from_dict({})
        assert tags.technology == []
        assert tags.feature == []
        assert tags.priority == Priority.MEDIUM.value


class TestCollectionItem:
    """Tests for CollectionItem model."""

    def test_create_item(self):
        """Test creating a collection item."""
        tags = CollectionTags(technology=["python"], feature=["testing"])
        item = CollectionItem(
            id="python-testing",
            name="Python Testing",
            item_type=ItemType.RULE,
            category="testing",
            file_path="rules/testing/python-testing.md",
            summary="Testing standards for Python",
            tags=tags,
        )

        assert item.id == "python-testing"
        assert item.name == "Python Testing"
        assert item.item_type == ItemType.RULE
        assert item.version == 1
        assert item.is_active is True

    def test_to_dict(self):
        """Test conversion to dictionary."""
        tags = CollectionTags(technology=["python"], priority="high")
        item = CollectionItem(
            id="test-item",
            name="Test Item",
            item_type=ItemType.SKILL,
            category="workflow",
            file_path="skills/test/SKILL.md",
            summary="Test skill",
            tags=tags,
            version=2,
        )
        result = item.to_dict()

        assert result["id"] == "test-item"
        assert result["item_type"] == "skill"
        assert result["tags"]["technology"] == ["python"]
        assert result["version"] == 2

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "id": "from-dict",
            "name": "From Dict",
            "item_type": "template",
            "category": "claude-md",
            "file_path": "templates/claude-md/test.md",
            "summary": "Test template",
            "tags": {"technology": ["react"], "feature": ["ui"], "priority": "low"},
            "version": 3,
            "is_active": True,
        }
        item = CollectionItem.from_dict(data)

        assert item.id == "from-dict"
        assert item.item_type == ItemType.TEMPLATE
        assert item.tags.technology == ["react"]
        assert item.version == 3


class TestProjectRequirements:
    """Tests for ProjectRequirements model."""

    def test_create_requirements(self):
        """Test creating project requirements."""
        reqs = ProjectRequirements(
            project_name="test-project",
            project_path=Path("/tmp/test"),
            technologies=["python", "fastapi"],
            features=["api", "auth", "database"],
            description="A test API project",
        )

        assert reqs.project_name == "test-project"
        assert len(reqs.technologies) == 2
        assert len(reqs.features) == 3

    def test_to_dict(self):
        """Test conversion to dictionary."""
        reqs = ProjectRequirements(
            project_name="my-app",
            project_path=Path("/home/user/my-app"),
            technologies=["typescript"],
            features=["frontend"],
        )
        result = reqs.to_dict()

        assert result["project_name"] == "my-app"
        assert result["project_path"] == "/home/user/my-app"
        assert result["technologies"] == ["typescript"]


class TestGapItem:
    """Tests for GapItem model."""

    def test_create_gap(self):
        """Test creating a gap item."""
        gap = GapItem(
            gap_type="technology",
            value="graphql",
            recommended_research="graphql best practices for AI agents",
        )

        assert gap.gap_type == "technology"
        assert gap.value == "graphql"
        assert "graphql" in gap.recommended_research


class TestSyncResult:
    """Tests for SyncResult model."""

    def test_default_values(self):
        """Test default sync result values."""
        result = SyncResult()
        assert result.items_added == 0
        assert result.items_updated == 0
        assert result.items_removed == 0
        assert result.errors == []

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = SyncResult(items_added=5, items_updated=2, errors=["Error 1"])
        data = result.to_dict()

        assert data["items_added"] == 5
        assert data["items_updated"] == 2
        assert len(data["errors"]) == 1


class TestCopyResult:
    """Tests for CopyResult model."""

    def test_create_result(self):
        """Test creating copy result."""
        result = CopyResult(
            project_name="my-project",
            items_copied=["item-1", "item-2"],
            files_created=["CLAUDE.md", "shared-rules/security.md"],
        )

        assert result.project_name == "my-project"
        assert len(result.items_copied) == 2
        assert len(result.files_created) == 2
