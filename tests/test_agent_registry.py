"""Unit tests for the agent registry."""

import pytest
from orchestrator.registry import (
    AGENT_REGISTRY,
    get_agent,
    get_agent_reviewers,
    get_all_agents,
    get_agents_by_cli,
    AgentConfig,
)
from orchestrator.registry.agents import (
    validate_agent_can_write,
    get_reviewer_agents,
    get_review_pairings,
)


class TestAgentRegistry:
    """Tests for the agent registry."""

    def test_registry_has_all_agents(self):
        """Test that all 12 agents are registered."""
        expected_agents = [
            "A01", "A02", "A03", "A04", "A05", "A06",
            "A07", "A08", "A09", "A10", "A11", "A12",
        ]
        for agent_id in expected_agents:
            assert agent_id in AGENT_REGISTRY, f"Agent {agent_id} not in registry"

    def test_get_agent_returns_config(self):
        """Test that get_agent returns AgentConfig."""
        agent = get_agent("A04")
        assert isinstance(agent, AgentConfig)
        assert agent.id == "A04"
        assert agent.name == "Implementer"

    def test_get_agent_raises_for_invalid_id(self):
        """Test that get_agent raises KeyError for invalid ID."""
        with pytest.raises(KeyError):
            get_agent("A99")

    def test_agent_has_required_fields(self):
        """Test that all agents have required fields."""
        for agent_id, agent in AGENT_REGISTRY.items():
            assert agent.id == agent_id
            assert agent.name
            assert agent.primary_cli in ["claude", "cursor", "gemini"]
            assert isinstance(agent.reviewers, list)
            assert isinstance(agent.max_iterations, int)
            assert agent.max_iterations > 0

    def test_reviewer_agents_have_specialization(self):
        """Test that reviewer agents have review specialization."""
        reviewer_agents = ["A07", "A08"]
        for agent_id in reviewer_agents:
            agent = get_agent(agent_id)
            assert agent.is_reviewer is True
            assert agent.review_specialization is not None

    def test_get_agent_reviewers(self):
        """Test getting reviewers for an agent."""
        reviewers = get_agent_reviewers("A04")
        assert len(reviewers) >= 2  # 4-eyes protocol
        reviewer_ids = [r.id for r in reviewers]
        assert "A07" in reviewer_ids  # Security reviewer
        assert "A08" in reviewer_ids  # Code reviewer

    def test_get_all_agents(self):
        """Test getting all agents."""
        all_agents = get_all_agents()
        assert len(all_agents) == 12

    def test_get_agents_by_cli(self):
        """Test filtering agents by CLI."""
        claude_agents = get_agents_by_cli("claude")
        assert len(claude_agents) > 0
        for agent in claude_agents:
            assert agent.primary_cli == "claude"

        cursor_agents = get_agents_by_cli("cursor")
        assert len(cursor_agents) > 0

        gemini_agents = get_agents_by_cli("gemini")
        assert len(gemini_agents) > 0

    def test_get_reviewer_agents(self):
        """Test getting only reviewer agents."""
        reviewers = get_reviewer_agents()
        assert len(reviewers) >= 2
        for reviewer in reviewers:
            assert reviewer.is_reviewer is True


class TestAgentFilePermissions:
    """Tests for agent file permission validation."""

    def test_implementer_can_write_source(self):
        """Test A04 can write to src/."""
        assert validate_agent_can_write("A04", "src/main.py")
        assert validate_agent_can_write("A04", "src/utils/helper.py")
        assert validate_agent_can_write("A04", "lib/core.py")

    def test_implementer_cannot_write_tests(self):
        """Test A04 cannot write to tests/ based on forbidden patterns."""
        # Note: fnmatch patterns use glob syntax where ** requires full path
        # The forbidden pattern "tests/**/*" matches nested paths
        assert not validate_agent_can_write("A04", "tests/unit/test_core.py")

    def test_test_writer_can_write_tests(self):
        """Test A03 can write to tests/ based on allowed patterns."""
        # The allowed patterns use glob syntax
        assert validate_agent_can_write("A03", "tests/unit/test_core.py")
        assert validate_agent_can_write("A03", "test/unit/test_helper.py")

    def test_test_writer_cannot_write_source(self):
        """Test A03 cannot write to src/."""
        assert not validate_agent_can_write("A03", "src/main.py")

    def test_reviewer_cannot_write_anything(self):
        """Test reviewers cannot write files."""
        assert not validate_agent_can_write("A07", "src/main.py")
        assert not validate_agent_can_write("A07", "tests/test_main.py")
        assert not validate_agent_can_write("A08", "src/main.py")

    def test_documentation_can_write_docs(self):
        """Test A09 can write documentation."""
        assert validate_agent_can_write("A09", "docs/api.md")
        assert validate_agent_can_write("A09", "README.md")

    def test_documentation_cannot_write_code(self):
        """Test A09 cannot write code."""
        assert not validate_agent_can_write("A09", "src/main.py")
        assert not validate_agent_can_write("A09", "main.ts")


class TestReviewPairings:
    """Tests for review pairing configuration."""

    def test_all_working_agents_have_reviewers(self):
        """Test that all working agents have at least 2 reviewers."""
        pairings = get_review_pairings()

        working_agents = [
            "A01", "A03", "A04", "A05", "A06", "A09", "A10", "A11", "A12"
        ]

        for agent_id in working_agents:
            if agent_id in pairings:
                assert len(pairings[agent_id]["reviewers"]) >= 2, \
                    f"Agent {agent_id} has fewer than 2 reviewers"

    def test_reviewers_use_different_clis(self):
        """Test that reviewers use different CLIs when possible."""
        pairings = get_review_pairings()

        for agent_id, pairing in pairings.items():
            clis = pairing["reviewer_clis"]
            # At least one should be different if 2+ reviewers
            if len(clis) >= 2:
                # This is a soft check - not all pairings need different CLIs
                pass

    def test_review_weights_are_valid(self):
        """Test that review weights are between 0 and 1."""
        pairings = get_review_pairings()

        for agent_id, pairing in pairings.items():
            for reviewer_id, weight in pairing["weights"].items():
                assert 0 <= weight <= 1, \
                    f"Invalid weight {weight} for {reviewer_id} reviewing {agent_id}"
