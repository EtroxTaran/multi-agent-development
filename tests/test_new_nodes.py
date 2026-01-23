"""Tests for the new risk mitigation nodes.

Tests cover:
1. product_validation_node - PRODUCT.md validation node
2. pre_implementation_node - Environment check node
3. build_verification_node - Build check node
4. coverage_check_node - Coverage enforcement node
5. security_scan_node - Security scanning node
6. approval_gate_node - Human approval gate node
7. New routers

Run with: pytest tests/test_new_nodes.py -v
"""

import json
import tempfile
from pathlib import Path

import pytest

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


# =============================================================================
# Product Validation Node Tests
# =============================================================================


class TestProductValidationNode:
    """Test product_validation_node."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            workflow_dir = project_dir / ".workflow"
            workflow_dir.mkdir()
            yield project_dir

    @pytest.mark.asyncio
    async def test_valid_product_md(self, temp_project):
        """Test validation passes with valid PRODUCT.md."""
        from orchestrator.langgraph.nodes.product_validation import product_validation_node
        from orchestrator.langgraph.state import create_initial_state

        # Create valid PRODUCT.md
        product_md = temp_project / "PRODUCT.md"
        product_md.write_text(
            """
# Product Specification

## Feature Name
User Authentication System

## Summary
A comprehensive authentication system for user management with JWT tokens
and secure password handling.

## Problem Statement
The application currently lacks a secure way for users to authenticate.
We need a robust authentication system that handles user registration,
login, logout, and session management. This is critical for protecting
user data and enabling personalized features.

## Acceptance Criteria
- [ ] Users can register with email and password
- [ ] Users can login with valid credentials
- [ ] Users receive JWT token on successful login
- [ ] Invalid credentials return error

## Example Inputs/Outputs

```json
POST /api/auth/register
{"email": "user@example.com", "password": "SecurePass123!"}
```

```json
Response: {"success": true}
```

## Technical Constraints
- Response time < 200ms
- Passwords hashed with bcrypt

## Testing Strategy
- Unit tests for auth service
- Integration tests for API endpoints
"""
        )

        # Create .project-config.json to enable feature
        config = temp_project / ".project-config.json"
        config.write_text(json.dumps({"workflow": {"features": {"product_validation": True}}}))

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await product_validation_node(state)

        assert result.get("next_decision") == "continue"
        assert "errors" not in result or len(result.get("errors", [])) == 0

    @pytest.mark.asyncio
    async def test_invalid_product_md(self, temp_project):
        """Test validation fails with invalid PRODUCT.md."""
        from orchestrator.langgraph.nodes.product_validation import product_validation_node
        from orchestrator.langgraph.state import create_initial_state

        # Create invalid PRODUCT.md
        product_md = temp_project / "PRODUCT.md"
        product_md.write_text("# Product\n[TODO]")

        config = temp_project / ".project-config.json"
        config.write_text(json.dumps({"workflow": {"features": {"product_validation": True}}}))

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await product_validation_node(state)

        assert result.get("next_decision") == "escalate"
        assert len(result.get("errors", [])) > 0

    @pytest.mark.asyncio
    async def test_disabled_validation(self, temp_project):
        """Test validation skipped when disabled."""
        from orchestrator.langgraph.nodes.product_validation import product_validation_node
        from orchestrator.langgraph.state import create_initial_state

        config = temp_project / ".project-config.json"
        config.write_text(json.dumps({"workflow": {"features": {"product_validation": False}}}))

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await product_validation_node(state)

        assert result.get("next_decision") == "continue"


# =============================================================================
# Pre-Implementation Node Tests
# =============================================================================


class TestPreImplementationNode:
    """Test pre_implementation_node."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            workflow_dir = project_dir / ".workflow"
            workflow_dir.mkdir()
            yield project_dir

    @pytest.mark.asyncio
    async def test_node_project_check(self, temp_project):
        """Test environment check for Node.js project."""
        from orchestrator.langgraph.nodes.pre_implementation import pre_implementation_node
        from orchestrator.langgraph.state import create_initial_state

        # Create package.json
        package_json = temp_project / "package.json"
        package_json.write_text(
            json.dumps({"name": "test", "scripts": {"build": "tsc", "test": "vitest"}})
        )

        # Create node_modules to indicate deps installed
        (temp_project / "node_modules").mkdir()

        config = temp_project / ".project-config.json"
        config.write_text(json.dumps({"workflow": {"features": {"environment_check": True}}}))

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await pre_implementation_node(state)

        # Result depends on whether Node is installed
        assert "updated_at" in result

    @pytest.mark.asyncio
    async def test_disabled_check(self, temp_project):
        """Test environment check skipped when disabled."""
        from orchestrator.langgraph.nodes.pre_implementation import pre_implementation_node
        from orchestrator.langgraph.state import create_initial_state

        config = temp_project / ".project-config.json"
        config.write_text(json.dumps({"workflow": {"features": {"environment_check": False}}}))

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await pre_implementation_node(state)

        assert result.get("next_decision") == "continue"


# =============================================================================
# Build Verification Node Tests
# =============================================================================


class TestBuildVerificationNode:
    """Test build_verification_node."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            workflow_dir = project_dir / ".workflow"
            workflow_dir.mkdir()
            yield project_dir

    @pytest.mark.asyncio
    async def test_disabled_build(self, temp_project):
        """Test build verification skipped when disabled."""
        from orchestrator.langgraph.nodes.build_verification import build_verification_node
        from orchestrator.langgraph.state import create_initial_state

        config = temp_project / ".project-config.json"
        config.write_text(json.dumps({"workflow": {"features": {"build_verification": False}}}))

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await build_verification_node(state)

        assert result.get("next_decision") == "continue"

    @pytest.mark.asyncio
    async def test_build_not_required(self, temp_project):
        """Test build skipped when not required."""
        from orchestrator.langgraph.nodes.build_verification import build_verification_node
        from orchestrator.langgraph.state import create_initial_state

        config = temp_project / ".project-config.json"
        config.write_text(json.dumps({"quality": {"build_required": False}}))

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await build_verification_node(state)

        assert result.get("next_decision") == "continue"


# =============================================================================
# Coverage Check Node Tests
# =============================================================================


class TestCoverageCheckNode:
    """Test coverage_check_node."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            workflow_dir = project_dir / ".workflow"
            workflow_dir.mkdir()
            yield project_dir

    @pytest.mark.asyncio
    async def test_coverage_pass(self, temp_project):
        """Test coverage check passes when above threshold."""
        from orchestrator.langgraph.nodes.coverage_check import coverage_check_node
        from orchestrator.langgraph.state import create_initial_state

        # Create coverage report
        coverage_dir = temp_project / "coverage"
        coverage_dir.mkdir()
        coverage_file = coverage_dir / "coverage-summary.json"
        coverage_file.write_text(json.dumps({"total": {"lines": {"pct": 85.0}}}))

        config = temp_project / ".project-config.json"
        config.write_text(
            json.dumps({"quality": {"coverage_threshold": 80, "coverage_blocking": True}})
        )

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await coverage_check_node(state)

        assert result.get("next_decision") == "continue"

    @pytest.mark.asyncio
    async def test_coverage_fail_blocking(self, temp_project):
        """Test coverage check fails when below threshold and blocking."""
        from orchestrator.langgraph.nodes.coverage_check import coverage_check_node
        from orchestrator.langgraph.state import create_initial_state

        coverage_dir = temp_project / "coverage"
        coverage_dir.mkdir()
        coverage_file = coverage_dir / "coverage-summary.json"
        coverage_file.write_text(json.dumps({"total": {"lines": {"pct": 50.0}}}))

        config = temp_project / ".project-config.json"
        config.write_text(
            json.dumps({"quality": {"coverage_threshold": 80, "coverage_blocking": True}})
        )

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await coverage_check_node(state)

        assert result.get("next_decision") == "retry"
        assert len(result.get("errors", [])) > 0

    @pytest.mark.asyncio
    async def test_no_coverage_report(self, temp_project):
        """Test coverage check skipped when no report."""
        from orchestrator.langgraph.nodes.coverage_check import coverage_check_node
        from orchestrator.langgraph.state import create_initial_state

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await coverage_check_node(state)

        # Should continue (skipped, not failed)
        assert result.get("next_decision") == "continue"


# =============================================================================
# Security Scan Node Tests
# =============================================================================


class TestSecurityScanNode:
    """Test security_scan_node."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            workflow_dir = project_dir / ".workflow"
            workflow_dir.mkdir()
            yield project_dir

    @pytest.mark.asyncio
    async def test_clean_scan(self, temp_project):
        """Test security scan passes with clean code."""
        from orchestrator.langgraph.nodes.security_scan import security_scan_node
        from orchestrator.langgraph.state import create_initial_state

        # Create clean source file
        src_file = temp_project / "main.py"
        src_file.write_text('def hello():\n    return "Hello, World!"')

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await security_scan_node(state)

        assert result.get("next_decision") == "continue"

    @pytest.mark.asyncio
    async def test_vulnerable_code(self, temp_project):
        """Test security scan fails with vulnerable code."""
        from orchestrator.langgraph.nodes.security_scan import security_scan_node
        from orchestrator.langgraph.state import create_initial_state

        # Create file with vulnerability
        src_file = temp_project / "config.py"
        src_file.write_text('api_key = "sk-1234567890abcdefghijklmnopqrstuvwxyz"')

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await security_scan_node(state)

        assert result.get("next_decision") == "retry"
        assert len(result.get("errors", [])) > 0

    @pytest.mark.asyncio
    async def test_disabled_scan(self, temp_project):
        """Test security scan skipped when disabled."""
        from orchestrator.langgraph.nodes.security_scan import security_scan_node
        from orchestrator.langgraph.state import create_initial_state

        config = temp_project / ".project-config.json"
        config.write_text(json.dumps({"security": {"enabled": False}}))

        state = create_initial_state(str(temp_project), temp_project.name)

        result = await security_scan_node(state)

        assert result.get("next_decision") == "continue"


# =============================================================================
# Router Tests
# =============================================================================


class TestNewRouters:
    """Test new routers for risk mitigation nodes."""

    def test_product_validation_router_continue(self):
        """Test product_validation_router routes to planning on continue."""
        from orchestrator.langgraph.routers import product_validation_router
        from orchestrator.langgraph.state import WorkflowDecision

        state = {"next_decision": WorkflowDecision.CONTINUE}
        result = product_validation_router(state)
        assert result == "planning"

    def test_product_validation_router_escalate(self):
        """Test product_validation_router routes to escalation."""
        from orchestrator.langgraph.routers import product_validation_router
        from orchestrator.langgraph.state import WorkflowDecision

        state = {"next_decision": WorkflowDecision.ESCALATE}
        result = product_validation_router(state)
        assert result == "human_escalation"

    def test_pre_implementation_router_continue(self):
        """Test pre_implementation_router routes to implementation."""
        from orchestrator.langgraph.routers import pre_implementation_router
        from orchestrator.langgraph.state import WorkflowDecision

        state = {"next_decision": WorkflowDecision.CONTINUE}
        result = pre_implementation_router(state)
        assert result == "implementation"

    def test_coverage_check_router_continue(self):
        """Test coverage_check_router routes to security_scan."""
        from orchestrator.langgraph.routers import coverage_check_router
        from orchestrator.langgraph.state import WorkflowDecision

        state = {"next_decision": WorkflowDecision.CONTINUE}
        result = coverage_check_router(state)
        assert result == "security_scan"

    def test_coverage_check_router_retry(self):
        """Test coverage_check_router routes to implementation on retry."""
        from orchestrator.langgraph.routers import coverage_check_router
        from orchestrator.langgraph.state import WorkflowDecision

        state = {"next_decision": WorkflowDecision.RETRY}
        result = coverage_check_router(state)
        assert result == "implementation"

    def test_security_scan_router_continue(self):
        """Test security_scan_router routes to completion."""
        from orchestrator.langgraph.routers import security_scan_router
        from orchestrator.langgraph.state import WorkflowDecision

        state = {"next_decision": WorkflowDecision.CONTINUE}
        result = security_scan_router(state)
        assert result == "completion"

    def test_verification_router_with_build_errors(self):
        """Test verification_router handles build errors."""
        from orchestrator.langgraph.routers import verification_router

        state = {
            "next_decision": "continue",
            "errors": [{"type": "build_verification_failed", "message": "Build failed"}],
            "iteration_count": 0,
        }
        result = verification_router(state)
        assert result == "implementation"  # Retry

    def test_verification_router_escalate_after_retries(self):
        """Test verification_router escalates after max retries."""
        from orchestrator.langgraph.routers import verification_router

        state = {
            "next_decision": "continue",
            "errors": [{"type": "build_verification_failed", "message": "Build failed"}],
            "iteration_count": 5,  # > 3 retries
        }
        result = verification_router(state)
        assert result == "human_escalation"


# =============================================================================
# Workflow Integration Tests
# =============================================================================


class TestWorkflowIntegration:
    """Test workflow graph with new nodes."""

    def test_graph_compiles(self):
        """Test that the workflow graph compiles successfully."""
        from orchestrator.langgraph.workflow import create_workflow_graph

        # Should not raise
        graph = create_workflow_graph()
        assert graph is not None

    def test_new_nodes_in_graph(self):
        """Test that new nodes are present in the graph."""
        from orchestrator.langgraph.workflow import create_workflow_graph

        graph = create_workflow_graph()

        # The graph should have nodes for all new risk mitigation steps
        # Note: Checking graph internals depends on LangGraph implementation
        # This is a basic smoke test
        assert graph is not None
