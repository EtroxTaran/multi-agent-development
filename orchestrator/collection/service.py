"""Collection service for managing rules, skills, and templates.

This service provides CRUD operations for the collection system,
syncing between filesystem and database, and querying with filters.
"""

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from ..db.connection import get_connection
from .models import CollectionItem, CollectionTags, ItemType, SyncResult

logger = logging.getLogger(__name__)

# Default collection directory
COLLECTION_DIR = Path(__file__).parent.parent.parent / "collection"


class CollectionService:
    """Manages the rules & skills collection.

    Provides CRUD operations, filesystem sync, and querying with filters.
    Uses SurrealDB for metadata and filesystem for content.
    """

    def __init__(self, collection_dir: Optional[Path] = None):
        """Initialize the collection service.

        Args:
            collection_dir: Path to collection directory (defaults to conductor/collection)
        """
        self.collection_dir = Path(collection_dir) if collection_dir else COLLECTION_DIR
        self._db_name = "conductor"  # Use main conductor database

    async def list_items(
        self,
        item_type: Optional[str] = None,
        technologies: Optional[list[str]] = None,
        features: Optional[list[str]] = None,
        priority: Optional[str] = None,
        include_content: bool = False,
    ) -> list[CollectionItem]:
        """List collection items with optional filters.

        Args:
            item_type: Filter by type (rule, skill, template)
            technologies: Filter by technology tags
            features: Filter by feature tags
            priority: Filter by priority
            include_content: Whether to load file content

        Returns:
            List of matching CollectionItem objects
        """
        async with get_connection(self._db_name) as conn:
            # Build query with filters
            conditions = ["is_active = true"]

            if item_type:
                conditions.append(f"item_type = '{item_type}'")

            if priority:
                conditions.append(f"tags.priority = '{priority}'")

            where_clause = " AND ".join(conditions)
            query = f"SELECT * FROM collection_items WHERE {where_clause} ORDER BY name"

            results = await conn.query(query)

            items = []
            for record in results:
                item = CollectionItem.from_dict(record)

                # Filter by technology tags (in-memory for array matching)
                if technologies:
                    item_techs = item.tags.technology
                    if not any(t in item_techs for t in technologies):
                        continue

                # Filter by feature tags
                if features:
                    item_features = item.tags.feature
                    if not any(f in item_features for f in features):
                        continue

                # Load content if requested
                if include_content:
                    item.content = self._load_file_content(item.file_path)

                items.append(item)

            return items

    async def get_item(
        self, item_id: str, include_content: bool = True
    ) -> Optional[CollectionItem]:
        """Get a single item by ID.

        Args:
            item_id: The item ID
            include_content: Whether to load file content

        Returns:
            CollectionItem or None if not found
        """
        async with get_connection(self._db_name) as conn:
            results = await conn.query(
                "SELECT * FROM collection_items WHERE id = $id",
                {"id": item_id},
            )

            if not results:
                return None

            item = CollectionItem.from_dict(results[0])

            if include_content:
                item.content = self._load_file_content(item.file_path)

            return item

    async def create_item(
        self,
        name: str,
        item_type: ItemType,
        category: str,
        content: str,
        tags: CollectionTags,
        summary: str = "",
    ) -> CollectionItem:
        """Create a new collection item.

        Creates both the file and database metadata.

        Args:
            name: Item name
            item_type: Type (rule, skill, template)
            category: Category within type
            content: Markdown content with frontmatter
            tags: Tags for the item
            summary: Brief summary

        Returns:
            Created CollectionItem
        """
        # Generate ID from name
        item_id = self._generate_id(name)

        # Determine file path based on type
        file_path = self._get_file_path(item_type, category, name)

        # Calculate content hash
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Create item
        item = CollectionItem(
            id=item_id,
            name=name,
            item_type=item_type,
            category=category,
            file_path=str(file_path),
            summary=summary,
            tags=tags,
            version=1,
            is_active=True,
            content_hash=content_hash,
            content=content,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        # Write file
        full_path = self.collection_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

        # Save to database
        async with get_connection(self._db_name) as conn:
            await conn.create("collection_items", item.to_dict(), item_id)

        logger.info(f"Created collection item: {item_id}")
        return item

    async def update_item(
        self,
        item_id: str,
        content: Optional[str] = None,
        tags: Optional[CollectionTags] = None,
        summary: Optional[str] = None,
    ) -> Optional[CollectionItem]:
        """Update an existing item.

        Args:
            item_id: Item ID to update
            content: New content (updates file)
            tags: New tags
            summary: New summary

        Returns:
            Updated CollectionItem or None if not found
        """
        item = await self.get_item(item_id, include_content=False)
        if not item:
            return None

        updates = {"updated_at": datetime.now().isoformat()}

        if content:
            # Update file
            full_path = self.collection_dir / item.file_path
            full_path.write_text(content)
            updates["content_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
            updates["version"] = item.version + 1

        if tags:
            updates["tags"] = tags.to_dict()

        if summary:
            updates["summary"] = summary

        async with get_connection(self._db_name) as conn:
            await conn.update(f"collection_items:{item_id}", updates)

        logger.info(f"Updated collection item: {item_id}")
        return await self.get_item(item_id)

    async def delete_item(self, item_id: str, hard_delete: bool = False) -> bool:
        """Delete an item (soft delete by default).

        Args:
            item_id: Item ID to delete
            hard_delete: If True, also delete the file

        Returns:
            True if deleted
        """
        item = await self.get_item(item_id, include_content=False)
        if not item:
            return False

        async with get_connection(self._db_name) as conn:
            if hard_delete:
                # Delete file
                full_path = self.collection_dir / item.file_path
                if full_path.exists():
                    full_path.unlink()

                # Delete from database
                await conn.delete(f"collection_items:{item_id}")
            else:
                # Soft delete
                await conn.update(
                    f"collection_items:{item_id}",
                    {"is_active": False, "updated_at": datetime.now().isoformat()},
                )

        logger.info(f"Deleted collection item: {item_id} (hard={hard_delete})")
        return True

    async def sync_from_filesystem(self) -> SyncResult:
        """Sync database metadata from filesystem.

        Scans the collection directory for files with YAML frontmatter
        and updates the database accordingly.

        Returns:
            SyncResult with counts of added/updated/removed items
        """
        result = SyncResult()

        # Get existing items from database
        async with get_connection(self._db_name) as conn:
            existing = await conn.query("SELECT * FROM collection_items")
            existing_by_path = {r["file_path"]: r for r in existing}

        # Scan filesystem
        found_paths = set()

        for item_type in ["rules", "skills", "templates"]:
            type_dir = self.collection_dir / item_type
            if not type_dir.exists():
                continue

            for file_path in type_dir.rglob("*.md"):
                if file_path.name == "README.md":
                    continue

                relative_path = str(file_path.relative_to(self.collection_dir))
                found_paths.add(relative_path)

                try:
                    metadata = self._parse_file_metadata(file_path)
                    if not metadata:
                        continue

                    content = file_path.read_text()
                    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

                    if relative_path in existing_by_path:
                        # Check if content changed
                        existing_item = existing_by_path[relative_path]
                        if existing_item.get("content_hash") != content_hash:
                            # Update
                            async with get_connection(self._db_name) as conn:
                                await conn.update(
                                    f"collection_items:`{existing_item['id']}`",
                                    {
                                        "tags": metadata.get("tags", {}),
                                        "summary": metadata.get("summary", ""),
                                        "content_hash": content_hash,
                                        "version": existing_item.get("version", 1) + 1,
                                        "updated_at": datetime.now().isoformat(),
                                    },
                                )
                            result.items_updated += 1
                    else:
                        # Create new
                        item_id = self._generate_id(metadata.get("name", file_path.stem))
                        item_type_enum = self._path_to_type(item_type)
                        category = self._extract_category(relative_path)

                        tags_data = metadata.get("tags", {})
                        tags = CollectionTags.from_dict(tags_data)

                        item = CollectionItem(
                            id=item_id,
                            name=metadata.get("name", file_path.stem),
                            item_type=item_type_enum,
                            category=category,
                            file_path=relative_path,
                            summary=metadata.get("summary", metadata.get("description", "")),
                            tags=tags,
                            version=metadata.get("version", 1),
                            is_active=True,
                            content_hash=content_hash,
                            created_at=datetime.now(),
                            updated_at=datetime.now(),
                        )

                        async with get_connection(self._db_name) as conn:
                            await conn.create("collection_items", item.to_dict(), item_id)
                        result.items_added += 1

                except Exception as e:
                    result.errors.append(f"Error processing {relative_path}: {e}")
                    logger.error(f"Error syncing {relative_path}: {e}")

        # Mark missing items as inactive
        for path, existing_item in existing_by_path.items():
            if path not in found_paths and existing_item.get("is_active", True):
                async with get_connection(self._db_name) as conn:
                    await conn.update(
                        f"collection_items:`{existing_item['id']}`",
                        {"is_active": False, "updated_at": datetime.now().isoformat()},
                    )
                result.items_removed += 1

        logger.info(
            f"Sync complete: +{result.items_added} ~{result.items_updated} -{result.items_removed}"
        )
        return result

    async def get_available_tags(self) -> dict[str, list[str]]:
        """Get all available tags grouped by type.

        Returns:
            Dictionary with technology, feature, and priority tag lists
        """
        async with get_connection(self._db_name) as conn:
            results = await conn.query("SELECT tags FROM collection_items WHERE is_active = true")

        technologies = set()
        features = set()
        priorities = set()

        for record in results:
            tags = record.get("tags", {})
            technologies.update(tags.get("technology", []))
            features.update(tags.get("feature", []))
            if tags.get("priority"):
                priorities.add(tags["priority"])

        return {
            "technology": sorted(technologies),
            "feature": sorted(features),
            "priority": sorted(priorities),
        }

    def _load_file_content(self, file_path: str) -> Optional[str]:
        """Load content from a file."""
        full_path = self.collection_dir / file_path
        if full_path.exists():
            return full_path.read_text()
        return None

    def _parse_file_metadata(self, file_path: Path) -> Optional[dict]:
        """Parse YAML frontmatter from a markdown file."""
        content = file_path.read_text()

        # Match YAML frontmatter
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return None

        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None

    def _generate_id(self, name: str) -> str:
        """Generate a URL-safe ID from a name."""
        # Convert to lowercase, replace spaces with hyphens
        id_str = name.lower().replace(" ", "-")
        # Remove non-alphanumeric characters except hyphens
        id_str = re.sub(r"[^a-z0-9-]", "", id_str)
        # Remove consecutive hyphens
        id_str = re.sub(r"-+", "-", id_str)
        return id_str.strip("-")

    def _get_file_path(self, item_type: ItemType, category: str, name: str) -> Path:
        """Get the file path for a new item."""
        type_dir = item_type.value + "s"  # rules, skills, templates
        filename = self._generate_id(name) + ".md"

        if item_type == ItemType.SKILL:
            # Skills use directory structure
            return Path(type_dir) / self._generate_id(name) / "SKILL.md"
        else:
            return Path(type_dir) / category / filename

    def _path_to_type(self, type_str: str) -> ItemType:
        """Convert path component to ItemType."""
        type_map = {
            "rules": ItemType.RULE,
            "skills": ItemType.SKILL,
            "templates": ItemType.TEMPLATE,
        }
        return type_map.get(type_str, ItemType.RULE)

    def _extract_category(self, file_path: str) -> str:
        """Extract category from file path."""
        parts = Path(file_path).parts
        if len(parts) >= 2:
            return parts[1]  # e.g., "coding-standards" from "rules/coding-standards/file.md"
        return ""
