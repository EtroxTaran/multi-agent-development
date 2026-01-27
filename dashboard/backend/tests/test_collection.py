"""Tests for collection API router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def mock_collection_service():
    """Create a mock CollectionService."""
    mock = MagicMock()
    mock.list_items = AsyncMock(return_value=[])
    mock.get_item = AsyncMock(return_value=None)
    mock.create_item = AsyncMock()
    mock.update_item = AsyncMock()
    mock.delete_item = AsyncMock(return_value=True)
    mock.get_available_tags = AsyncMock(
        return_value={
            "technology": ["python", "typescript"],
            "feature": ["security", "testing"],
            "priority": ["high", "medium", "low"],
        }
    )
    return mock


@pytest.fixture
def sample_collection_item():
    """Create a sample collection item."""
    from orchestrator.collection import ItemType

    mock_item = MagicMock()
    mock_item.id = "rule-001"
    mock_item.name = "python-standards"
    # Use real ItemType enum for isinstance check in _item_to_response
    mock_item.item_type = ItemType.RULE
    mock_item.category = "coding-standards"
    mock_item.file_path = "/collection/rules/coding-standards/python-standards.md"
    mock_item.summary = "Python coding standards"
    mock_item.tags = MagicMock()
    mock_item.tags.technology = ["python"]
    mock_item.tags.feature = ["coding"]
    mock_item.tags.priority = "high"
    mock_item.version = 1
    mock_item.is_active = True
    mock_item.content = "# Python Standards\n\nFollow PEP8."
    return mock_item


class TestListItems:
    """Tests for GET /api/collection/items endpoint."""

    def test_list_items_empty(self, mock_collection_service: MagicMock):
        """Test listing items when collection is empty."""
        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.get("/api/collection/items")

            assert response.status_code == 200
            data = response.json()
            # Response is now paginated
            assert data["items"] == []
            assert data["total"] == 0

    def test_list_items_with_items(
        self, mock_collection_service: MagicMock, sample_collection_item: MagicMock
    ):
        """Test listing items when items exist."""
        mock_collection_service.list_items = AsyncMock(return_value=[sample_collection_item])

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.get("/api/collection/items")

            assert response.status_code == 200
            data = response.json()
            # Response is now paginated
            assert len(data["items"]) == 1
            assert data["items"][0]["id"] == "rule-001"
            assert data["items"][0]["name"] == "python-standards"

    def test_list_items_with_type_filter(self, mock_collection_service: MagicMock):
        """Test listing items with type filter."""
        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.get("/api/collection/items?item_type=rule")

            assert response.status_code == 200
            mock_collection_service.list_items.assert_called_once()
            call_kwargs = mock_collection_service.list_items.call_args[1]
            assert call_kwargs["item_type"] == "rule"

    def test_list_items_with_technology_filter(self, mock_collection_service: MagicMock):
        """Test listing items with technology filter."""
        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.get("/api/collection/items?technologies=python,typescript")

            assert response.status_code == 200
            call_kwargs = mock_collection_service.list_items.call_args[1]
            assert call_kwargs["technologies"] == ["python", "typescript"]


class TestGetItem:
    """Tests for GET /api/collection/items/{item_id} endpoint."""

    def test_get_item_success(
        self, mock_collection_service: MagicMock, sample_collection_item: MagicMock
    ):
        """Test getting an existing item."""
        mock_collection_service.get_item = AsyncMock(return_value=sample_collection_item)

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.get("/api/collection/items/rule-001")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "rule-001"
            assert data["content"] == "# Python Standards\n\nFollow PEP8."

    def test_get_item_not_found(self, mock_collection_service: MagicMock):
        """Test getting a non-existent item."""
        mock_collection_service.get_item = AsyncMock(return_value=None)

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.get("/api/collection/items/nonexistent")

            assert response.status_code == 404


class TestCreateItem:
    """Tests for POST /api/collection/items endpoint."""

    def test_create_item_success(
        self, mock_collection_service: MagicMock, sample_collection_item: MagicMock
    ):
        """Test creating a new item."""
        mock_collection_service.create_item = AsyncMock(return_value=sample_collection_item)

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.post(
                "/api/collection/items",
                json={
                    "name": "python-standards",
                    "item_type": "rule",
                    "category": "coding-standards",
                    "content": "# Python Standards",
                    "tags": {"technology": ["python"], "feature": ["coding"], "priority": "high"},
                    "summary": "Python coding standards",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "python-standards"

    def test_create_item_invalid_type(self, mock_collection_service: MagicMock):
        """Test creating item with invalid type."""
        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.post(
                "/api/collection/items",
                json={
                    "name": "test",
                    "item_type": "invalid",
                    "category": "test",
                    "content": "test",
                    "tags": {"technology": [], "feature": [], "priority": "medium"},
                },
            )

            assert response.status_code == 400


class TestUpdateItem:
    """Tests for PUT /api/collection/items/{item_id} endpoint."""

    def test_update_item_success(
        self, mock_collection_service: MagicMock, sample_collection_item: MagicMock
    ):
        """Test updating an existing item."""
        mock_collection_service.update_item = AsyncMock(return_value=sample_collection_item)

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.put(
                "/api/collection/items/rule-001",
                json={"content": "# Updated content", "summary": "Updated summary"},
            )

            assert response.status_code == 200

    def test_update_item_not_found(self, mock_collection_service: MagicMock):
        """Test updating a non-existent item."""
        mock_collection_service.update_item = AsyncMock(return_value=None)

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.put("/api/collection/items/nonexistent", json={"content": "test"})

            assert response.status_code == 404


class TestDeleteItem:
    """Tests for DELETE /api/collection/items/{item_id} endpoint."""

    def test_delete_item_success(self, mock_collection_service: MagicMock):
        """Test deleting an item."""
        mock_collection_service.delete_item = AsyncMock(return_value=True)

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.delete("/api/collection/items/rule-001")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    def test_delete_item_not_found(self, mock_collection_service: MagicMock):
        """Test deleting a non-existent item."""
        mock_collection_service.delete_item = AsyncMock(return_value=False)

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.delete("/api/collection/items/nonexistent")

            assert response.status_code == 404


class TestListTags:
    """Tests for GET /api/collection/tags endpoint."""

    def test_list_tags(self, mock_collection_service: MagicMock):
        """Test listing available tags."""
        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.get("/api/collection/tags")

            assert response.status_code == 200
            data = response.json()
            assert "technology" in data
            assert "feature" in data
            assert "priority" in data


class TestItemToResponse:
    """Tests for _item_to_response conversion function.

    These tests ensure proper handling of SurrealDB types during serialization.
    """

    def test_item_id_converted_to_string(self):
        """Test that SurrealDB RecordID is properly converted to string.

        This is a regression test for a bug where RecordID objects were passed
        directly to Pydantic models, causing validation errors:
        'Input should be a valid string, input_type=RecordID'
        """
        from orchestrator.collection import ItemType

        from app.routers.collection import _item_to_response

        # Create a mock item with a RecordID-like object for id
        class MockRecordID:
            """Simulates SurrealDB RecordID object."""

            def __init__(self, table_name: str, record_id: str):
                self.table_name = table_name
                self.record_id = record_id

            def __str__(self):
                return f"{self.table_name}:{self.record_id}"

        mock_item = MagicMock()
        mock_item.id = MockRecordID("collection_items", "test-rule")
        mock_item.name = "Test Rule"
        mock_item.item_type = ItemType.RULE
        mock_item.category = "test"
        mock_item.file_path = "rules/test.md"
        mock_item.summary = "Test summary"
        mock_item.tags = MagicMock()
        mock_item.tags.technology = ["python"]
        mock_item.tags.feature = ["testing"]
        mock_item.tags.priority = "high"
        mock_item.version = 1
        mock_item.is_active = True
        mock_item.content = None

        # This should not raise a validation error
        response = _item_to_response(mock_item)

        # The id should be converted to a string
        assert isinstance(response.id, str)
        assert response.id == "collection_items:test-rule"

    def test_item_with_string_id_unchanged(self):
        """Test that items with string IDs are handled correctly."""
        from orchestrator.collection import ItemType

        from app.routers.collection import _item_to_response

        mock_item = MagicMock()
        mock_item.id = "simple-string-id"
        mock_item.name = "Test Rule"
        mock_item.item_type = ItemType.RULE
        mock_item.category = "test"
        mock_item.file_path = "rules/test.md"
        mock_item.summary = "Test summary"
        mock_item.tags = MagicMock()
        mock_item.tags.technology = ["python"]
        mock_item.tags.feature = ["testing"]
        mock_item.tags.priority = "high"
        mock_item.version = 1
        mock_item.is_active = True
        mock_item.content = None

        response = _item_to_response(mock_item)

        assert isinstance(response.id, str)
        assert response.id == "simple-string-id"

    def test_list_items_returns_string_ids(self, mock_collection_service: MagicMock):
        """Test that list_items endpoint returns items with string IDs.

        This is an integration test ensuring the full pipeline handles
        RecordID conversion correctly.
        """
        from orchestrator.collection import ItemType

        # Create a mock item with a RecordID-like object
        class MockRecordID:
            def __init__(self, table_name: str, record_id: str):
                self.table_name = table_name
                self.record_id = record_id

            def __str__(self):
                return f"{self.table_name}:{self.record_id}"

        mock_item = MagicMock()
        mock_item.id = MockRecordID("collection_items", "security-guardrails")
        mock_item.name = "Security Guardrails"
        mock_item.item_type = ItemType.RULE
        mock_item.category = "guardrails"
        mock_item.file_path = "rules/guardrails/security.md"
        mock_item.summary = "Security rules"
        mock_item.tags = MagicMock()
        mock_item.tags.technology = ["python"]
        mock_item.tags.feature = ["security"]
        mock_item.tags.priority = "critical"
        mock_item.version = 1
        mock_item.is_active = True
        mock_item.content = None

        mock_collection_service.list_items = AsyncMock(return_value=[mock_item])

        with patch("app.routers.collection.collection_service", mock_collection_service):
            client = TestClient(app)
            response = client.get("/api/collection/items")

            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 1
            # ID must be a string, not an object
            assert isinstance(data["items"][0]["id"], str)
            assert data["items"][0]["id"] == "collection_items:security-guardrails"
