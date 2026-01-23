"""Tests for Linear integration adapter.

Tests cover:
1. LinearConfig loading
2. LinearAdapter initialization
3. Issue creation (mocked)
4. Status updates
5. Graceful degradation

Run with: pytest tests/test_linear_integration.py -v
"""

import json
from unittest.mock import patch

import pytest

# =============================================================================
# Test LinearConfig
# =============================================================================


class TestLinearConfig:
    """Test Linear configuration loading."""

    def test_default_config(self):
        """Test default configuration values."""
        from orchestrator.langgraph.integrations.linear import LinearConfig

        config = LinearConfig()

        assert config.enabled is False
        assert config.team_id is None
        assert config.create_project is True
        assert "pending" in config.status_mapping
        assert config.status_mapping["pending"] == "Backlog"

    def test_load_config_no_file(self, temp_project_dir):
        """Test loading when no config file exists."""
        from orchestrator.langgraph.integrations.linear import load_linear_config

        config = load_linear_config(temp_project_dir)

        assert config.enabled is False
        assert config.team_id is None

    def test_load_config_with_linear_section(self, temp_project_dir):
        """Test loading config with Linear section."""
        from orchestrator.langgraph.integrations.linear import load_linear_config

        config_content = {
            "project_type": "node-api",
            "integrations": {
                "linear": {
                    "enabled": True,
                    "team_id": "TEAM123",
                    "create_project": False,
                }
            },
        }
        (temp_project_dir / ".project-config.json").write_text(json.dumps(config_content))

        config = load_linear_config(temp_project_dir)

        assert config.enabled is True
        assert config.team_id == "TEAM123"
        assert config.create_project is False

    def test_load_config_invalid_json(self, temp_project_dir):
        """Test loading with invalid JSON returns defaults."""
        from orchestrator.langgraph.integrations.linear import load_linear_config

        (temp_project_dir / ".project-config.json").write_text("invalid json")

        config = load_linear_config(temp_project_dir)

        assert config.enabled is False


# =============================================================================
# Test LinearAdapter
# =============================================================================


class TestLinearAdapter:
    """Test Linear adapter functionality."""

    def test_adapter_disabled(self):
        """Test adapter behavior when disabled."""
        from orchestrator.langgraph.integrations.linear import LinearAdapter, LinearConfig

        config = LinearConfig(enabled=False)
        adapter = LinearAdapter(config)

        assert adapter.enabled is False

    def test_adapter_enabled_no_team_id(self):
        """Test adapter requires team_id when enabled."""
        from orchestrator.langgraph.integrations.linear import LinearAdapter, LinearConfig

        config = LinearConfig(enabled=True, team_id=None)
        adapter = LinearAdapter(config)

        # Should be disabled without team_id
        assert adapter.enabled is False

    def test_adapter_enabled_with_team_id(self):
        """Test adapter enabled with team_id."""
        from orchestrator.langgraph.integrations.linear import LinearAdapter, LinearConfig

        config = LinearConfig(enabled=True, team_id="TEAM123")
        adapter = LinearAdapter(config)

        assert adapter.enabled is True

    def test_create_issues_disabled(self):
        """Test create_issues returns empty when disabled."""
        from orchestrator.langgraph.integrations.linear import LinearAdapter, LinearConfig

        config = LinearConfig(enabled=False)
        adapter = LinearAdapter(config)

        tasks = [{"id": "T1", "title": "Test task"}]
        result = adapter.create_issues_from_tasks(tasks, "Test Project")

        assert result == {}

    def test_update_status_disabled(self):
        """Test update_status returns True when disabled."""
        from orchestrator.langgraph.integrations.linear import LinearAdapter, LinearConfig
        from orchestrator.langgraph.state import TaskStatus

        config = LinearConfig(enabled=False)
        adapter = LinearAdapter(config)

        result = adapter.update_issue_status("T1", TaskStatus.COMPLETED)

        assert result is True  # No error

    def test_add_blocker_comment_disabled(self):
        """Test add_blocker returns True when disabled."""
        from orchestrator.langgraph.integrations.linear import LinearAdapter, LinearConfig

        config = LinearConfig(enabled=False)
        adapter = LinearAdapter(config)

        result = adapter.add_blocker_comment("T1", "Blocked on X")

        assert result is True  # No error

    def test_status_mapping(self):
        """Test task status to Linear status mapping."""
        from orchestrator.langgraph.integrations.linear import LinearConfig
        from orchestrator.langgraph.state import TaskStatus

        config = LinearConfig()

        assert config.status_mapping[TaskStatus.PENDING.value] == "Backlog"
        assert config.status_mapping[TaskStatus.IN_PROGRESS.value] == "In Progress"
        assert config.status_mapping[TaskStatus.COMPLETED.value] == "Done"
        assert config.status_mapping[TaskStatus.BLOCKED.value] == "Blocked"


# =============================================================================
# Test Issue Mapping Persistence
# =============================================================================


class TestIssueMappingPersistence:
    """Test saving and loading issue mappings."""

    def test_save_issue_mapping(self, temp_project_dir):
        """Test saving task to issue mapping."""
        from orchestrator.langgraph.integrations.linear import save_issue_mapping

        mapping = {
            "T1": "LINEAR-123",
            "T2": "LINEAR-456",
        }

        save_issue_mapping(temp_project_dir, mapping)

        mapping_file = temp_project_dir / ".workflow" / "linear_issues.json"
        assert mapping_file.exists()

        loaded = json.loads(mapping_file.read_text())
        assert loaded["T1"] == "LINEAR-123"
        assert loaded["T2"] == "LINEAR-456"

    def test_save_issue_mapping_empty(self, temp_project_dir):
        """Test saving empty mapping does nothing."""
        from orchestrator.langgraph.integrations.linear import save_issue_mapping

        save_issue_mapping(temp_project_dir, {})

        mapping_file = temp_project_dir / ".workflow" / "linear_issues.json"
        assert not mapping_file.exists()

    def test_load_issue_mapping(self, temp_project_dir):
        """Test loading task to issue mapping."""
        from orchestrator.langgraph.integrations.linear import load_issue_mapping

        workflow_dir = temp_project_dir / ".workflow"
        workflow_dir.mkdir()
        (workflow_dir / "linear_issues.json").write_text(
            json.dumps(
                {
                    "T1": "LINEAR-123",
                }
            )
        )

        mapping = load_issue_mapping(temp_project_dir)

        assert mapping["T1"] == "LINEAR-123"

    def test_load_issue_mapping_no_file(self, temp_project_dir):
        """Test loading when no mapping file exists."""
        from orchestrator.langgraph.integrations.linear import load_issue_mapping

        mapping = load_issue_mapping(temp_project_dir)

        assert mapping == {}

    def test_load_issue_mapping_invalid_json(self, temp_project_dir):
        """Test loading with invalid JSON."""
        from orchestrator.langgraph.integrations.linear import load_issue_mapping

        workflow_dir = temp_project_dir / ".workflow"
        workflow_dir.mkdir()
        (workflow_dir / "linear_issues.json").write_text("invalid")

        mapping = load_issue_mapping(temp_project_dir)

        assert mapping == {}


# =============================================================================
# Test Factory Function
# =============================================================================


class TestLinearAdapterFactory:
    """Test adapter factory function."""

    def test_create_linear_adapter(self, temp_project_dir):
        """Test creating adapter with factory."""
        from orchestrator.langgraph.integrations.linear import create_linear_adapter

        adapter = create_linear_adapter(temp_project_dir)

        # Default config should be disabled
        assert adapter.enabled is False

    def test_create_linear_adapter_with_config(self, temp_project_dir):
        """Test creating adapter with config file."""
        from orchestrator.langgraph.integrations.linear import create_linear_adapter

        config_content = {
            "integrations": {
                "linear": {
                    "enabled": True,
                    "team_id": "TEAM123",
                }
            }
        }
        (temp_project_dir / ".project-config.json").write_text(json.dumps(config_content))

        adapter = create_linear_adapter(temp_project_dir)

        assert adapter.enabled is True


# =============================================================================
# Test MCP Availability Check
# =============================================================================


class TestMCPAvailability:
    """Test MCP availability detection."""

    def test_mcp_not_available_when_command_fails(self):
        """Test MCP is detected as unavailable when command fails."""
        from orchestrator.langgraph.integrations.linear import LinearAdapter, LinearConfig

        config = LinearConfig(enabled=True, team_id="TEAM123")
        adapter = LinearAdapter(config)

        # Mock the MCP command to return None (simulating unavailable)
        with patch.object(adapter, "_run_mcp_command", return_value=None):
            # Reset cached availability
            adapter._mcp_available = None
            result = adapter._check_mcp_available()
            assert result is False

    def test_mcp_available_when_returns_teams(self):
        """Test MCP is detected as available when it returns teams."""
        from orchestrator.langgraph.integrations.linear import LinearAdapter, LinearConfig

        config = LinearConfig(enabled=True, team_id="TEAM123")
        adapter = LinearAdapter(config)

        # Mock the MCP command to return valid response
        with patch.object(adapter, "_run_mcp_command", return_value='{"teams": []}'):
            # Reset cached availability
            adapter._mcp_available = None
            result = adapter._check_mcp_available()
            assert result is True


# =============================================================================
# Test Integration Exports
# =============================================================================


class TestIntegrationExports:
    """Test integrations __init__ exports."""

    def test_linear_exports(self):
        """Test Linear classes are exported from integrations."""
        from orchestrator.langgraph.integrations import (
            LinearAdapter,
            LinearConfig,
            create_linear_adapter,
        )

        # Just verify imports work
        assert LinearAdapter is not None
        assert LinearConfig is not None
        assert create_linear_adapter is not None


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
