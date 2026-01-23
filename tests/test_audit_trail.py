"""Unit tests for AuditTrail."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from orchestrator.audit import (
    AuditConfig,
    AuditEntry,
    AuditTrail,
    create_audit_trail,
    get_project_audit_trail,
)


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project = tmp_path / "test-project"
    project.mkdir()
    return project


@pytest.fixture
def audit_trail(temp_project: Path) -> AuditTrail:
    """Create an audit trail for testing."""
    return AuditTrail(temp_project)


class TestAuditEntry:
    """Tests for AuditEntry dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        entry = AuditEntry(
            id="audit-001",
            timestamp="2024-01-15T10:00:00",
            agent="claude",
            task_id="T1",
            session_id="sess-123",
            prompt_hash="abc123",
            prompt_length=100,
        )
        data = entry.to_dict()

        assert data["id"] == "audit-001"
        assert data["agent"] == "claude"
        assert data["task_id"] == "T1"
        assert data["session_id"] == "sess-123"
        # Internal fields should not be serialized
        assert "_start_time" not in data
        assert "_prompt" not in data

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "id": "audit-002",
            "timestamp": "2024-01-15T11:00:00",
            "agent": "cursor",
            "task_id": "T2",
            "status": "success",
            "duration_seconds": 15.5,
        }
        entry = AuditEntry.from_dict(data)

        assert entry.id == "audit-002"
        assert entry.agent == "cursor"
        assert entry.status == "success"
        assert entry.duration_seconds == 15.5

    def test_set_result_success(self):
        """Test setting successful result."""
        entry = AuditEntry(
            id="test",
            timestamp="2024-01-15T10:00:00",
            agent="claude",
            task_id="T1",
        )
        entry._start_time = datetime.now() - timedelta(seconds=5)

        entry.set_result(
            success=True,
            exit_code=0,
            output="output text",
            parsed_output={"model": "claude-3-opus"},
            cost_usd=0.05,
        )

        assert entry.status == "success"
        assert entry.exit_code == 0
        assert entry.output_length == len("output text")
        assert entry.model == "claude-3-opus"
        assert entry.cost_usd == 0.05
        assert entry.duration_seconds > 0

    def test_set_result_failure(self):
        """Test setting failed result."""
        entry = AuditEntry(
            id="test",
            timestamp="2024-01-15T10:00:00",
            agent="claude",
            task_id="T1",
        )
        entry._start_time = datetime.now()

        entry.set_result(
            success=False,
            exit_code=1,
            error="Something went wrong",
        )

        assert entry.status == "failed"
        assert entry.exit_code == 1
        assert entry.error_length > 0

    def test_set_timeout(self):
        """Test setting timeout status."""
        entry = AuditEntry(
            id="test",
            timestamp="2024-01-15T10:00:00",
            agent="claude",
            task_id="T1",
        )

        entry.set_timeout(300)

        assert entry.status == "timeout"
        assert entry.duration_seconds == 300
        assert entry.exit_code == -1

    def test_set_error(self):
        """Test setting error status."""
        entry = AuditEntry(
            id="test",
            timestamp="2024-01-15T10:00:00",
            agent="claude",
            task_id="T1",
        )
        entry._start_time = datetime.now()

        entry.set_error("CLI not found")

        assert entry.status == "error"
        assert entry.metadata["error_message"] == "CLI not found"


class TestAuditTrail:
    """Tests for AuditTrail."""

    def test_start_entry(self, audit_trail: AuditTrail):
        """Test starting a new audit entry."""
        entry = audit_trail.start_entry(
            agent="claude",
            task_id="T1",
            prompt="Test prompt",
            session_id="sess-123",
        )

        assert entry.agent == "claude"
        assert entry.task_id == "T1"
        assert entry.session_id == "sess-123"
        assert entry.prompt_length == len("Test prompt")
        assert entry.prompt_hash  # Should have a hash
        assert entry._start_time is not None

    def test_commit_entry(self, audit_trail: AuditTrail, temp_project: Path):
        """Test committing an entry."""
        entry = audit_trail.start_entry(
            agent="claude",
            task_id="T1",
            prompt="Test prompt",
        )
        entry.set_result(success=True, exit_code=0)

        audit_trail.commit_entry(entry)

        # Verify entry was written
        log_file = temp_project / ".workflow" / "audit" / "invocations.jsonl"
        assert log_file.exists()

        with open(log_file) as f:
            lines = f.readlines()
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["id"] == entry.id

    def test_record_context_manager(self, audit_trail: AuditTrail):
        """Test recording with context manager."""
        with audit_trail.record(
            agent="claude",
            task_id="T1",
            prompt="Test prompt",
        ) as entry:
            entry.set_result(success=True, exit_code=0, output="test output")

        # Entry should be committed
        entries = audit_trail.query(task_id="T1")
        assert len(entries) == 1
        assert entries[0].status == "success"

    def test_record_context_manager_exception(self, audit_trail: AuditTrail):
        """Test recording handles exceptions."""
        with pytest.raises(ValueError):
            with audit_trail.record(
                agent="claude",
                task_id="T1",
                prompt="Test prompt",
            ) as entry:
                raise ValueError("Test error")

        # Entry should still be committed with error status
        entries = audit_trail.query(task_id="T1")
        assert len(entries) == 1
        assert entries[0].status == "error"

    def test_query_by_task_id(self, audit_trail: AuditTrail):
        """Test querying by task ID."""
        # Add multiple entries
        for i, task_id in enumerate(["T1", "T1", "T2", "T3"]):
            with audit_trail.record(agent="claude", task_id=task_id, prompt=f"prompt {i}") as entry:
                entry.set_result(success=True, exit_code=0)

        results = audit_trail.query(task_id="T1")
        assert len(results) == 2
        for entry in results:
            assert entry.task_id == "T1"

    def test_query_by_agent(self, audit_trail: AuditTrail):
        """Test querying by agent."""
        agents = ["claude", "cursor", "claude", "gemini"]
        for i, agent in enumerate(agents):
            with audit_trail.record(agent=agent, task_id=f"T{i}", prompt=f"prompt {i}") as entry:
                entry.set_result(success=True, exit_code=0)

        results = audit_trail.query(agent="claude")
        assert len(results) == 2

    def test_query_by_status(self, audit_trail: AuditTrail):
        """Test querying by status."""
        statuses = [True, False, True, True]
        for i, success in enumerate(statuses):
            with audit_trail.record(agent="claude", task_id=f"T{i}", prompt=f"prompt {i}") as entry:
                entry.set_result(success=success, exit_code=0 if success else 1)

        successes = audit_trail.query(status="success")
        failures = audit_trail.query(status="failed")

        assert len(successes) == 3
        assert len(failures) == 1

    def test_query_with_limit(self, audit_trail: AuditTrail):
        """Test query with limit."""
        for i in range(10):
            with audit_trail.record(agent="claude", task_id=f"T{i}", prompt=f"prompt {i}") as entry:
                entry.set_result(success=True, exit_code=0)

        results = audit_trail.query(limit=5)
        assert len(results) == 5

    def test_get_task_history(self, audit_trail: AuditTrail):
        """Test getting task history."""
        # Add entries in mixed order
        for task_id in ["T1", "T2", "T1", "T1"]:
            with audit_trail.record(agent="claude", task_id=task_id, prompt="test") as entry:
                entry.set_result(success=True, exit_code=0)

        history = audit_trail.get_task_history("T1")
        assert len(history) == 3
        # Should be chronologically ordered
        for i in range(len(history) - 1):
            assert history[i].timestamp <= history[i + 1].timestamp

    def test_get_statistics(self, audit_trail: AuditTrail):
        """Test getting statistics."""
        # Add varied entries
        configs = [
            ("claude", True, 0.05),
            ("claude", True, 0.03),
            ("claude", False, 0.02),
            ("cursor", True, None),
            ("gemini", True, None),
        ]
        for i, (agent, success, cost) in enumerate(configs):
            with audit_trail.record(agent=agent, task_id=f"T{i}", prompt="test") as entry:
                entry.set_result(success=success, exit_code=0 if success else 1, cost_usd=cost)

        stats = audit_trail.get_statistics()

        assert stats["total"] == 5
        assert stats["success_count"] == 4
        assert stats["failed_count"] == 1
        assert stats["success_rate"] == 0.8
        assert stats["total_cost_usd"] == 0.10  # 0.05 + 0.03 + 0.02
        assert stats["by_agent"]["claude"] == 3
        assert stats["by_agent"]["cursor"] == 1
        assert stats["by_agent"]["gemini"] == 1

    def test_disabled_audit(self, temp_project: Path):
        """Test that disabled audit trail doesn't write."""
        config = AuditConfig(enabled=False)
        trail = AuditTrail(temp_project, config=config)

        with trail.record(agent="claude", task_id="T1", prompt="test") as entry:
            entry.set_result(success=True, exit_code=0)

        log_file = temp_project / ".workflow" / "audit" / "invocations.jsonl"
        assert not log_file.exists()


class TestAuditConfig:
    """Tests for AuditConfig."""

    def test_defaults(self):
        """Test default configuration."""
        config = AuditConfig()

        assert config.audit_dir == ".workflow/audit"
        assert config.log_file == "invocations.jsonl"
        assert config.max_log_size_mb == 50
        assert config.max_log_age_days == 30
        assert config.enabled is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = AuditConfig(
            audit_dir="custom/audit",
            max_log_size_mb=100,
            enabled=False,
        )

        assert config.audit_dir == "custom/audit"
        assert config.max_log_size_mb == 100
        assert config.enabled is False


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_audit_trail(self, temp_project: Path):
        """Test create_audit_trail function."""
        trail = create_audit_trail(temp_project)
        assert trail is not None
        assert trail.project_dir == temp_project

    def test_get_project_audit_trail_caching(self, temp_project: Path):
        """Test that get_project_audit_trail caches instances."""
        trail1 = get_project_audit_trail(temp_project)
        trail2 = get_project_audit_trail(temp_project)

        assert trail1 is trail2  # Same instance
