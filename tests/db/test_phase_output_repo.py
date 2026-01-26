"""Tests for phase output repository.

Tests the PhaseOutputRepository class and PhaseOutput dataclass
from orchestrator.db.repositories.phase_outputs module.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.db.repositories.phase_outputs import (
    OutputType,
    PhaseOutput,
    PhaseOutputRepository,
    get_phase_output_repository,
)


class TestPhaseOutput:
    """Tests for the PhaseOutput dataclass."""

    def test_phase_output_defaults(self):
        """Test PhaseOutput default values."""
        output = PhaseOutput(phase=1, output_type="plan")
        assert output.phase == 1
        assert output.output_type == "plan"
        assert output.content == {}
        assert output.task_id is None
        assert output.id is None

    def test_phase_output_with_content(self):
        """Test PhaseOutput with content."""
        content = {"plan_name": "Test Plan", "tasks": []}
        output = PhaseOutput(
            phase=1,
            output_type=OutputType.PLAN,
            content=content,
        )
        assert output.content == content

    def test_phase_output_to_dict(self):
        """Test converting PhaseOutput to dictionary."""
        output = PhaseOutput(
            phase=2,
            output_type=OutputType.CURSOR_FEEDBACK,
            content={"score": 8.5},
            task_id="T1",
        )
        data = output.to_dict()

        assert data["phase"] == 2
        assert data["output_type"] == "cursor_feedback"
        assert data["content"] == {"score": 8.5}
        assert data["task_id"] == "T1"
        assert "id" not in data  # id should be excluded


class TestOutputType:
    """Tests for OutputType constants."""

    def test_output_type_plan(self):
        """Test plan output type."""
        assert OutputType.PLAN == "plan"

    def test_output_type_validation(self):
        """Test validation output types."""
        assert OutputType.CURSOR_FEEDBACK == "cursor_feedback"
        assert OutputType.GEMINI_FEEDBACK == "gemini_feedback"

    def test_output_type_implementation(self):
        """Test implementation output type."""
        assert OutputType.TASK_RESULT == "task_result"

    def test_output_type_verification(self):
        """Test verification output types."""
        assert OutputType.CURSOR_REVIEW == "cursor_review"
        assert OutputType.GEMINI_REVIEW == "gemini_review"

    def test_output_type_completion(self):
        """Test completion output type."""
        assert OutputType.SUMMARY == "summary"


class TestPhaseOutputRepository:
    """Tests for the PhaseOutputRepository class."""

    @pytest.fixture
    def repo(self):
        """Create a PhaseOutputRepository for testing."""
        return PhaseOutputRepository("test-project")

    @pytest.fixture
    def mock_conn(self):
        """Create a mock database connection."""
        conn = MagicMock()
        conn.query = AsyncMock(return_value=[])
        conn.create = AsyncMock(return_value={"id": "phase_outputs:123"})
        conn.update = AsyncMock(return_value={"id": "phase_outputs:123"})
        return conn

    def test_repository_init(self, repo):
        """Test repository initialization."""
        assert repo.project_name == "test-project"
        assert repo.table_name == "phase_outputs"

    def test_to_record_with_dict(self, repo):
        """Test _to_record with a dictionary."""
        data = {
            "id": "phase_outputs:123",
            "phase": 1,
            "output_type": "plan",
            "content": {"name": "Test"},
        }
        result = repo._to_record(data)

        assert isinstance(result, PhaseOutput)
        assert result.phase == 1
        assert result.output_type == "plan"

    def test_to_record_with_string(self, repo):
        """Test _to_record with a string ID."""
        result = repo._to_record("phase_outputs:123")

        assert isinstance(result, PhaseOutput)
        assert result.id == "phase_outputs:123"
        assert result.phase == 0

    def test_to_record_with_none(self, repo):
        """Test _to_record with None."""
        result = repo._to_record(None)

        assert isinstance(result, PhaseOutput)
        assert result.phase == 0

    @pytest.mark.asyncio
    async def test_save_output_creates_new(self, repo, mock_conn):
        """Test save_output creates new record when none exists."""
        mock_conn.query = AsyncMock(return_value=[])  # No existing
        mock_conn.create = AsyncMock(
            return_value={
                "id": "phase_outputs:new",
                "phase": 1,
                "output_type": "plan",
                "content": {"name": "Test"},
            }
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_output(1, "plan", {"name": "Test"})

            assert result.phase == 1
            mock_conn.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_output_updates_existing(self, repo, mock_conn):
        """Test save_output updates existing record."""
        mock_conn.query = AsyncMock(return_value=[{"id": "phase_outputs:existing", "phase": 1}])
        mock_conn.update = AsyncMock(
            return_value={
                "id": "phase_outputs:existing",
                "phase": 1,
                "output_type": "plan",
                "content": {"updated": True},
            }
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_output(1, "plan", {"updated": True})

            assert result is not None
            mock_conn.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_output_with_task_id(self, repo, mock_conn):
        """Test save_output with task ID."""
        mock_conn.query = AsyncMock(return_value=[])
        mock_conn.create = AsyncMock(
            return_value={
                "id": "phase_outputs:new",
                "phase": 3,
                "output_type": "task_result",
                "task_id": "T1",
            }
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_output(3, "task_result", {"done": True}, "T1")

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_output_found(self, repo, mock_conn):
        """Test get_output when output exists."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "id": "phase_outputs:123",
                    "phase": 1,
                    "output_type": "plan",
                    "content": {"name": "Test"},
                }
            ]
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_output(1, "plan")

            assert result is not None
            assert result.content == {"name": "Test"}

    @pytest.mark.asyncio
    async def test_get_output_not_found(self, repo, mock_conn):
        """Test get_output when output doesn't exist."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_output(1, "plan")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_phase_outputs(self, repo, mock_conn):
        """Test getting all outputs for a phase."""
        mock_conn.query = AsyncMock(
            return_value=[
                {"id": "1", "phase": 2, "output_type": "cursor_feedback"},
                {"id": "2", "phase": 2, "output_type": "gemini_feedback"},
            ]
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            results = await repo.get_phase_outputs(2)

            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_get_task_outputs(self, repo, mock_conn):
        """Test getting all outputs for a task."""
        mock_conn.query = AsyncMock(
            return_value=[
                {"id": "1", "phase": 3, "output_type": "task_result", "task_id": "T1"},
            ]
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            results = await repo.get_task_outputs("T1")

            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_save_plan(self, repo, mock_conn):
        """Test save_plan convenience method."""
        mock_conn.query = AsyncMock(return_value=[])
        mock_conn.create = AsyncMock(return_value={"id": "new", "phase": 1, "output_type": "plan"})

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            plan = {"plan_name": "Test", "tasks": []}
            result = await repo.save_plan(plan)

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_plan(self, repo, mock_conn):
        """Test get_plan convenience method."""
        mock_conn.query = AsyncMock(
            return_value=[
                {"id": "1", "phase": 1, "output_type": "plan", "content": {"name": "Test"}}
            ]
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_plan()

            assert result == {"name": "Test"}

    @pytest.mark.asyncio
    async def test_get_plan_not_found(self, repo, mock_conn):
        """Test get_plan when no plan exists."""
        mock_conn.query = AsyncMock(return_value=[])

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_plan()

            assert result is None

    @pytest.mark.asyncio
    async def test_save_cursor_feedback(self, repo, mock_conn):
        """Test save_cursor_feedback convenience method."""
        mock_conn.query = AsyncMock(return_value=[])
        mock_conn.create = AsyncMock(
            return_value={"id": "new", "phase": 2, "output_type": "cursor_feedback"}
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_cursor_feedback({"score": 8.0})

            assert result is not None

    @pytest.mark.asyncio
    async def test_save_gemini_feedback(self, repo, mock_conn):
        """Test save_gemini_feedback convenience method."""
        mock_conn.query = AsyncMock(return_value=[])
        mock_conn.create = AsyncMock(
            return_value={"id": "new", "phase": 2, "output_type": "gemini_feedback"}
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_gemini_feedback({"score": 9.0})

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_validation_feedback(self, repo, mock_conn):
        """Test get_validation_feedback convenience method."""
        call_count = [0]

        async def mock_query(sql, params=None):
            call_count[0] += 1
            if "cursor_feedback" in sql or (
                params and params.get("output_type") == "cursor_feedback"
            ):
                return [{"id": "1", "content": {"score": 8.0}}]
            elif "gemini_feedback" in sql or (
                params and params.get("output_type") == "gemini_feedback"
            ):
                return [{"id": "2", "content": {"score": 9.0}}]
            return []

        mock_conn.query = AsyncMock(side_effect=mock_query)

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_validation_feedback()

            assert "cursor" in result
            assert "gemini" in result

    @pytest.mark.asyncio
    async def test_save_task_result(self, repo, mock_conn):
        """Test save_task_result convenience method."""
        mock_conn.query = AsyncMock(return_value=[])
        mock_conn.create = AsyncMock(
            return_value={
                "id": "new",
                "phase": 3,
                "output_type": "task_result",
                "task_id": "T1",
            }
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_task_result("T1", {"success": True})

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_task_result(self, repo, mock_conn):
        """Test get_task_result convenience method."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "id": "1",
                    "phase": 3,
                    "output_type": "task_result",
                    "content": {"success": True},
                    "task_id": "T1",
                }
            ]
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_task_result("T1")

            assert result == {"success": True}

    @pytest.mark.asyncio
    async def test_save_cursor_review(self, repo, mock_conn):
        """Test save_cursor_review convenience method."""
        mock_conn.query = AsyncMock(return_value=[])
        mock_conn.create = AsyncMock(
            return_value={"id": "new", "phase": 4, "output_type": "cursor_review"}
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_cursor_review({"approved": True})

            assert result is not None

    @pytest.mark.asyncio
    async def test_save_gemini_review(self, repo, mock_conn):
        """Test save_gemini_review convenience method."""
        mock_conn.query = AsyncMock(return_value=[])
        mock_conn.create = AsyncMock(
            return_value={"id": "new", "phase": 4, "output_type": "gemini_review"}
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_gemini_review({"approved": True})

            assert result is not None

    @pytest.mark.asyncio
    async def test_save_summary(self, repo, mock_conn):
        """Test save_summary convenience method."""
        mock_conn.query = AsyncMock(return_value=[])
        mock_conn.create = AsyncMock(
            return_value={"id": "new", "phase": 5, "output_type": "summary"}
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.save_summary({"completed": True})

            assert result is not None

    @pytest.mark.asyncio
    async def test_get_summary(self, repo, mock_conn):
        """Test get_summary convenience method."""
        mock_conn.query = AsyncMock(
            return_value=[
                {
                    "id": "1",
                    "phase": 5,
                    "output_type": "summary",
                    "content": {"completed": True},
                }
            ]
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await repo.get_summary()

            assert result == {"completed": True}

    @pytest.mark.asyncio
    async def test_clear_phase(self, repo, mock_conn):
        """Test clearing all outputs for a phase."""
        mock_conn.query = AsyncMock(
            return_value=[{"id": "1"}, {"id": "2"}, {"id": "3"}]  # 3 deleted
        )

        with patch("orchestrator.db.repositories.phase_outputs.get_connection") as mock_get_conn:
            mock_get_conn.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_get_conn.return_value.__aexit__ = AsyncMock(return_value=None)

            deleted = await repo.clear_phase(2)

            assert deleted == 3


class TestGetPhaseOutputRepository:
    """Tests for get_phase_output_repository function."""

    def test_creates_new_repository(self):
        """Test creating a new repository."""
        with patch("orchestrator.db.repositories.phase_outputs._repos", {}):
            repo = get_phase_output_repository("test-project")
            assert repo is not None
            assert repo.project_name == "test-project"

    def test_reuses_existing_repository(self):
        """Test reusing an existing repository."""
        with patch("orchestrator.db.repositories.phase_outputs._repos", {}):
            repo1 = get_phase_output_repository("test-project")
            repo2 = get_phase_output_repository("test-project")
            assert repo1 is repo2

    def test_different_projects_different_repos(self):
        """Test different projects get different repositories."""
        with patch("orchestrator.db.repositories.phase_outputs._repos", {}):
            repo1 = get_phase_output_repository("project-a")
            repo2 = get_phase_output_repository("project-b")
            assert repo1 is not repo2
