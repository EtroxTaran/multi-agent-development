"""Tests for health endpoint."""

from datetime import datetime


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_returns_healthy(self, test_client):
        """Health endpoint should return healthy status."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "orchestrator-api"

    def test_health_includes_timestamp(self, test_client):
        """Health endpoint should include a valid ISO timestamp."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data

        # Verify it's a valid ISO format
        timestamp = data["timestamp"]
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

    def test_health_response_structure(self, test_client):
        """Health endpoint should return the expected structure."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        expected_keys = {"status", "service", "timestamp"}
        assert set(data.keys()) == expected_keys
