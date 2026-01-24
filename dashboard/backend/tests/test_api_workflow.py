from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def mock_orchestrator():
    with patch("app.routers.workflow.Orchestrator") as mock:
        yield mock


def test_start_workflow_success(mock_orchestrator):
    # Setup
    instance = mock_orchestrator.return_value
    instance.check_prerequisites.return_value = (True, [])
    instance.run_langgraph.return_value = {"success": True}

    # Execute
    response = client.post(
        "/api/projects/test-project/start",
        json={"start_phase": 1, "end_phase": 5, "skip_validation": False, "autonomous": False},
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_start_workflow_prerequisites_failed(mock_orchestrator):
    # Setup
    instance = mock_orchestrator.return_value
    instance.check_prerequisites.return_value = (False, ["Missing PRODUCT.md"])

    # Execute
    response = client.post(
        "/api/projects/test-project/start", json={"start_phase": 1, "end_phase": 5}
    )

    # Assert
    assert response.status_code == 400
    data = response.json()
    assert "error" in data["detail"]
    assert data["detail"]["error"] == "Prerequisites not met"
    assert "Missing PRODUCT.md" in data["detail"]["details"]
