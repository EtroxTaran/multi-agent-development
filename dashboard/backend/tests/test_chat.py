"""Tests for chat API router."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import deps
from app.main import app


@pytest.fixture
def mock_websocket_manager():
    """Create a mock WebSocket manager."""
    mock = MagicMock()
    mock.broadcast_to_project = MagicMock()
    return mock


class TestSendChatMessage:
    """Tests for POST /chat endpoint."""

    def test_send_chat_message_success(self, mock_project_manager: MagicMock):
        """Test sending chat message successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Hello from Claude!"
        mock_result.stderr = ""

        mock_project_manager.get_project.return_value = Path("/test/project")
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            with patch("subprocess.run", return_value=mock_result):
                client = TestClient(app)
                response = client.post(
                    "/api/chat", json={"message": "Hello", "project_name": "test-project"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["message"] == "Hello from Claude!"
                assert data["streaming"] is False
        finally:
            app.dependency_overrides.clear()

    def test_send_chat_message_without_project(self):
        """Test sending chat message without project name."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Response"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            client = TestClient(app)
            response = client.post("/api/chat", json={"message": "Hello"})

            assert response.status_code == 200

    def test_send_chat_message_project_not_found(self, mock_project_manager: MagicMock):
        """Test sending chat message with non-existent project."""
        mock_project_manager.get_project.return_value = None
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            client = TestClient(app)
            response = client.post(
                "/api/chat", json={"message": "Hello", "project_name": "nonexistent"}
            )

            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_send_chat_message_timeout(self, mock_project_manager: MagicMock):
        """Test chat message timeout."""
        import subprocess

        mock_project_manager.get_project.return_value = Path("/test")
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 300)):
                client = TestClient(app)
                response = client.post(
                    "/api/chat", json={"message": "Hello", "project_name": "test"}
                )

                assert response.status_code == 504
        finally:
            app.dependency_overrides.clear()

    def test_send_chat_message_claude_not_found(self, mock_project_manager: MagicMock):
        """Test chat when Claude CLI not found."""
        mock_project_manager.get_project.return_value = Path("/test")
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            with patch("subprocess.run", side_effect=FileNotFoundError()):
                client = TestClient(app)
                response = client.post(
                    "/api/chat", json={"message": "Hello", "project_name": "test"}
                )

                assert response.status_code == 500
                assert "Claude CLI not found" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()


class TestExecuteCommand:
    """Tests for POST /chat/command endpoint."""

    def test_execute_command_success(self, mock_project_manager: MagicMock):
        """Test executing command successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Command output"
        mock_result.stderr = ""

        mock_project_manager.get_project.return_value = Path("/test")
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            with patch("subprocess.run", return_value=mock_result):
                client = TestClient(app)
                response = client.post(
                    "/api/chat/command", json={"command": "help", "project_name": "test"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["output"] == "Command output"
        finally:
            app.dependency_overrides.clear()

    def test_execute_command_with_args(self, mock_project_manager: MagicMock):
        """Test executing command with arguments."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Output"
        mock_result.stderr = ""

        mock_project_manager.get_project.return_value = Path("/test")
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            with patch("subprocess.run", return_value=mock_result):
                client = TestClient(app)
                response = client.post(
                    "/api/chat/command",
                    json={"command": "search", "args": ["pattern"], "project_name": "test"},
                )

                assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()

    def test_execute_command_timeout(self, mock_project_manager: MagicMock):
        """Test command timeout."""
        import subprocess

        mock_project_manager.get_project.return_value = Path("/test")
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager

        try:
            # Use a valid command from the allowed list
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 300)):
                client = TestClient(app)
                response = client.post(
                    "/api/chat/command", json={"command": "status", "project_name": "test"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is False
                assert "timed out" in data["error"]
        finally:
            app.dependency_overrides.clear()


class TestGetPhaseFeedback:
    """Tests for GET /projects/{project_name}/feedback/{phase} endpoint."""

    def test_get_phase_feedback_validation(
        self, temp_project_dir: Path, mock_project_manager: MagicMock
    ):
        """Test getting validation phase feedback."""
        # Create feedback files
        phase_dir = temp_project_dir / ".workflow" / "phases" / "validation"
        phase_dir.mkdir(parents=True)

        cursor_feedback = {"approved": True, "score": 8}
        (phase_dir / "cursor_feedback.json").write_text(json.dumps(cursor_feedback))

        mock_project_manager.get_project.return_value = temp_project_dir
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager
        app.dependency_overrides[deps.get_project_dir] = lambda project_name: temp_project_dir

        try:
            client = TestClient(app)
            response = client.get("/api/projects/test-project/feedback/2")

            assert response.status_code == 200
            data = response.json()
            assert "cursor" in data
            assert data["cursor"]["approved"] is True
        finally:
            app.dependency_overrides.clear()

    def test_get_phase_feedback_invalid_phase(
        self, temp_project_dir: Path, mock_project_manager: MagicMock
    ):
        """Test getting feedback for invalid phase."""
        mock_project_manager.get_project.return_value = temp_project_dir
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager
        app.dependency_overrides[deps.get_project_dir] = lambda project_name: temp_project_dir

        try:
            client = TestClient(app)
            response = client.get("/api/projects/test-project/feedback/3")

            assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_get_phase_feedback_not_found(
        self, temp_project_dir: Path, mock_project_manager: MagicMock
    ):
        """Test getting feedback when phase doesn't exist."""
        mock_project_manager.get_project.return_value = temp_project_dir
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager
        app.dependency_overrides[deps.get_project_dir] = lambda project_name: temp_project_dir

        try:
            client = TestClient(app)
            response = client.get("/api/projects/test-project/feedback/2")

            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestRespondToEscalation:
    """Tests for POST /projects/{project_name}/escalation/respond endpoint."""

    def test_respond_to_escalation(self, temp_project_dir: Path, mock_project_manager: MagicMock):
        """Test responding to an escalation."""
        mock_project_manager.get_project.return_value = temp_project_dir
        app.dependency_overrides[deps.get_project_manager] = lambda: mock_project_manager
        app.dependency_overrides[deps.get_project_dir] = lambda project_name: temp_project_dir

        try:
            with patch("app.routers.chat.get_connection_manager") as mock_manager:
                from unittest.mock import AsyncMock

                mock_manager.return_value.broadcast_to_project = AsyncMock()

                client = TestClient(app)
                response = client.post(
                    "/api/projects/test-project/escalation/respond",
                    json={
                        "question_id": "q-123",
                        "answer": "Yes, proceed",
                        "additional_context": "Extra info",
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["message"] == "Response recorded"
                assert data["question_id"] == "q-123"

                # Verify response file was created
                response_file = (
                    temp_project_dir / ".workflow" / "escalations" / "q-123_response.json"
                )
                assert response_file.exists()
        finally:
            app.dependency_overrides.clear()
