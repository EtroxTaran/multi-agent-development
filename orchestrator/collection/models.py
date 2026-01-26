"""Collection system data models.

Defines the data structures for rules, skills, templates,
and gap analysis results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class ItemType(str, Enum):
    """Type of collection item."""

    RULE = "rule"
    SKILL = "skill"
    TEMPLATE = "template"


class TagType(str, Enum):
    """Type of tag."""

    TECHNOLOGY = "technology"
    FEATURE = "feature"
    PRIORITY = "priority"


class Priority(str, Enum):
    """Priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class CollectionTags:
    """Tags for a collection item."""

    technology: list[str] = field(default_factory=list)
    feature: list[str] = field(default_factory=list)
    priority: str = Priority.MEDIUM.value

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "technology": self.technology,
            "feature": self.feature,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CollectionTags":
        """Create from dictionary."""
        return cls(
            technology=data.get("technology", []),
            feature=data.get("feature", []),
            priority=data.get("priority", Priority.MEDIUM.value),
        )


@dataclass
class CollectionItem:
    """A single item in the collection (rule, skill, or template)."""

    id: str
    name: str
    item_type: ItemType
    category: str
    file_path: str
    summary: str
    tags: CollectionTags
    version: int = 1
    is_active: bool = True
    content_hash: Optional[str] = None
    content: Optional[str] = None  # Loaded on demand
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "name": self.name,
            "item_type": self.item_type.value
            if isinstance(self.item_type, ItemType)
            else self.item_type,
            "category": self.category,
            "file_path": self.file_path,
            "summary": self.summary,
            "tags": self.tags.to_dict() if isinstance(self.tags, CollectionTags) else self.tags,
            "version": self.version,
            "is_active": self.is_active,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CollectionItem":
        """Create from dictionary."""
        tags_data = data.get("tags", {})
        if isinstance(tags_data, dict):
            tags = CollectionTags.from_dict(tags_data)
        else:
            tags = CollectionTags()

        item_type = data.get("item_type", "rule")
        if isinstance(item_type, str):
            item_type = ItemType(item_type)

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            item_type=item_type,
            category=data.get("category", ""),
            file_path=data.get("file_path", ""),
            summary=data.get("summary", ""),
            tags=tags,
            version=data.get("version", 1),
            is_active=data.get("is_active", True),
            content_hash=data.get("content_hash"),
            content=data.get("content"),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
        )


@dataclass
class ProjectRequirements:
    """Extracted requirements from a project's documentation."""

    project_name: str
    project_path: Path
    technologies: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "project_name": self.project_name,
            "project_path": str(self.project_path),
            "technologies": self.technologies,
            "features": self.features,
            "description": self.description,
        }


@dataclass
class GapItem:
    """A gap identified during analysis."""

    gap_type: str  # "technology" or "feature"
    value: str  # The missing technology/feature
    recommended_research: str  # Suggested search query

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "gap_type": self.gap_type,
            "value": self.value,
            "recommended_research": self.recommended_research,
        }


@dataclass
class GapAnalysisResult:
    """Result of gap analysis for a project."""

    project_name: str
    requirements: ProjectRequirements
    matching_items: list[CollectionItem] = field(default_factory=list)
    gaps: list[GapItem] = field(default_factory=list)
    analyzed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "project_name": self.project_name,
            "requirements": self.requirements.to_dict(),
            "matching_items": [item.to_dict() for item in self.matching_items],
            "gaps": [gap.to_dict() for gap in self.gaps],
            "analyzed_at": self.analyzed_at.isoformat() if self.analyzed_at else None,
        }


@dataclass
class SyncResult:
    """Result of syncing filesystem to database."""

    items_added: int = 0
    items_updated: int = 0
    items_removed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "items_added": self.items_added,
            "items_updated": self.items_updated,
            "items_removed": self.items_removed,
            "errors": self.errors,
        }


@dataclass
class CopyResult:
    """Result of copying items to a project."""

    project_name: str
    items_copied: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "project_name": self.project_name,
            "items_copied": self.items_copied,
            "files_created": self.files_created,
            "errors": self.errors,
        }
