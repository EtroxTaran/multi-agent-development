"""Tests for general workflow routers.

Tests routing logic for prerequisites, planning, implementation,
and completion phases.
"""


from orchestrator.langgraph.routers.general import (
    approval_gate_router,
    build_verification_router,
    completion_router,
    coverage_check_router,
    discuss_router,
    documentation_discovery_router,
    human_escalation_router,
    implementation_router,
    planning_router,
    pre_implementation_router,
    prerequisites_router,
    product_validation_router,
    research_router,
    security_scan_router,
)
from orchestrator.langgraph.state import PhaseState, PhaseStatus, WorkflowDecision


class TestPrerequisitesRouter:
    """Tests for prerequisites_router."""

    def test_continue_routes_to_planning(self):
        """Test continue decision routes to planning."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert prerequisites_router(state) == "planning"

    def test_continue_string_routes_to_planning(self):
        """Test continue as string routes to planning."""
        state = {"next_decision": "continue"}
        assert prerequisites_router(state) == "planning"

    def test_escalate_routes_to_human(self):
        """Test escalate decision routes to human_escalation."""
        state = {"next_decision": WorkflowDecision.ESCALATE}
        assert prerequisites_router(state) == "human_escalation"

    def test_abort_routes_to_end(self):
        """Test abort decision routes to __end__."""
        state = {"next_decision": WorkflowDecision.ABORT}
        assert prerequisites_router(state) == "__end__"

    def test_abort_string_routes_to_end(self):
        """Test abort as string routes to __end__."""
        state = {"next_decision": "abort"}
        assert prerequisites_router(state) == "__end__"

    def test_blocking_error_routes_to_human(self):
        """Test blocking error routes to human_escalation."""
        state = {
            "next_decision": None,
            "errors": [{"type": "missing_product_md", "blocking": True}],
        }
        assert prerequisites_router(state) == "human_escalation"

    def test_no_agents_error_routes_to_human(self):
        """Test no agents error routes to human_escalation."""
        state = {
            "next_decision": None,
            "errors": [{"type": "no_agents_available"}],
        }
        assert prerequisites_router(state) == "human_escalation"

    def test_default_routes_to_planning(self):
        """Test default routes to planning."""
        state = {"next_decision": None}
        assert prerequisites_router(state) == "planning"


class TestPlanningRouter:
    """Tests for planning_router."""

    def test_continue_routes_to_validation(self):
        """Test continue decision routes to cursor_validate."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert planning_router(state) == "cursor_validate"

    def test_escalate_routes_to_human(self):
        """Test escalate decision routes to human_escalation."""
        state = {"next_decision": WorkflowDecision.ESCALATE}
        assert planning_router(state) == "human_escalation"

    def test_abort_routes_to_end(self):
        """Test abort decision routes to __end__."""
        state = {"next_decision": WorkflowDecision.ABORT}
        assert planning_router(state) == "__end__"

    def test_valid_plan_routes_to_validation(self):
        """Test valid plan routes to cursor_validate."""
        state = {
            "next_decision": None,
            "plan": {"plan_name": "Test Plan"},
        }
        assert planning_router(state) == "cursor_validate"

    def test_completed_phase_routes_to_validation(self):
        """Test completed phase 1 routes to cursor_validate."""
        state = {
            "next_decision": None,
            "phase_status": {"1": PhaseState(status=PhaseStatus.COMPLETED)},
        }
        assert planning_router(state) == "cursor_validate"

    def test_failed_phase_max_attempts_routes_to_human(self):
        """Test failed phase at max attempts routes to human_escalation."""
        state = {
            "next_decision": None,
            "phase_status": {
                "1": PhaseState(status=PhaseStatus.FAILED, attempts=3, max_attempts=3)
            },
        }
        assert planning_router(state) == "human_escalation"

    def test_no_plan_routes_to_human(self):
        """Test no plan routes to human_escalation."""
        state = {"next_decision": None}
        assert planning_router(state) == "human_escalation"


class TestImplementationRouter:
    """Tests for implementation_router."""

    def test_continue_routes_to_review(self):
        """Test continue decision routes to cursor_review."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert implementation_router(state) == "cursor_review"

    def test_retry_routes_to_planning(self):
        """Test retry decision routes back to planning."""
        state = {"next_decision": WorkflowDecision.RETRY}
        assert implementation_router(state) == "planning"

    def test_escalate_routes_to_human(self):
        """Test escalate decision routes to human_escalation."""
        state = {"next_decision": WorkflowDecision.ESCALATE}
        assert implementation_router(state) == "human_escalation"

    def test_abort_routes_to_end(self):
        """Test abort decision routes to __end__."""
        state = {"next_decision": WorkflowDecision.ABORT}
        assert implementation_router(state) == "__end__"

    def test_completed_phase_routes_to_review(self):
        """Test completed phase routes to cursor_review."""
        state = {
            "next_decision": None,
            "phase_status": {"3": PhaseState(status=PhaseStatus.COMPLETED)},
        }
        assert implementation_router(state) == "cursor_review"

    def test_successful_implementation_routes_to_review(self):
        """Test successful implementation routes to cursor_review."""
        state = {
            "next_decision": None,
            "implementation_result": {"success": True},
        }
        assert implementation_router(state) == "cursor_review"

    def test_test_failures_routes_to_planning(self):
        """Test test failures route back to planning."""
        state = {
            "next_decision": None,
            "implementation_result": {"test_results": {"failed": 3}},
        }
        assert implementation_router(state) == "planning"

    def test_default_routes_to_review(self):
        """Test default routes to cursor_review."""
        state = {"next_decision": None}
        assert implementation_router(state) == "cursor_review"


class TestCompletionRouter:
    """Tests for completion_router."""

    def test_always_routes_to_end(self):
        """Test completion always routes to __end__."""
        states = [
            {"next_decision": WorkflowDecision.CONTINUE},
            {"next_decision": "continue"},
            {"next_decision": None},
            {},
        ]
        for state in states:
            assert completion_router(state) == "__end__"


class TestHumanEscalationRouter:
    """Tests for human_escalation_router."""

    def test_continue_early_phase_routes_to_planning(self):
        """Test continue in early phase routes to planning."""
        state = {
            "next_decision": WorkflowDecision.CONTINUE,
            "current_phase": 1,
        }
        assert human_escalation_router(state) == "planning"

    def test_continue_mid_phase_routes_to_implementation(self):
        """Test continue in mid phase routes to implementation."""
        state = {
            "next_decision": WorkflowDecision.CONTINUE,
            "current_phase": 3,
        }
        assert human_escalation_router(state) == "implementation"

    def test_continue_late_phase_routes_to_completion(self):
        """Test continue in late phase routes to completion."""
        state = {
            "next_decision": WorkflowDecision.CONTINUE,
            "current_phase": 4,
        }
        assert human_escalation_router(state) == "completion"

    def test_retry_early_phase_routes_to_planning(self):
        """Test retry in early phase routes to planning."""
        state = {
            "next_decision": WorkflowDecision.RETRY,
            "current_phase": 2,
        }
        assert human_escalation_router(state) == "planning"

    def test_retry_late_phase_routes_to_implementation(self):
        """Test retry in late phase routes to implementation."""
        state = {
            "next_decision": WorkflowDecision.RETRY,
            "current_phase": 4,
        }
        assert human_escalation_router(state) == "implementation"

    def test_default_routes_to_end(self):
        """Test default routes to __end__."""
        state = {"next_decision": None}
        assert human_escalation_router(state) == "__end__"


class TestProductValidationRouter:
    """Tests for product_validation_router."""

    def test_continue_routes_to_planning(self):
        """Test continue decision routes to planning."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert product_validation_router(state) == "planning"

    def test_escalate_routes_to_human(self):
        """Test escalate decision routes to human_escalation."""
        state = {"next_decision": WorkflowDecision.ESCALATE}
        assert product_validation_router(state) == "human_escalation"

    def test_abort_routes_to_end(self):
        """Test abort decision routes to __end__."""
        state = {"next_decision": WorkflowDecision.ABORT}
        assert product_validation_router(state) == "__end__"


class TestDocumentationDiscoveryRouter:
    """Tests for documentation_discovery_router."""

    def test_continue_routes_to_planning(self):
        """Test continue decision routes to planning."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert documentation_discovery_router(state) == "planning"

    def test_escalate_routes_to_human(self):
        """Test escalate decision routes to human_escalation."""
        state = {"next_decision": WorkflowDecision.ESCALATE}
        assert documentation_discovery_router(state) == "human_escalation"


class TestPreImplementationRouter:
    """Tests for pre_implementation_router."""

    def test_continue_routes_to_implementation(self):
        """Test continue decision routes to implementation."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert pre_implementation_router(state) == "implementation"

    def test_escalate_routes_to_human(self):
        """Test escalate decision routes to human_escalation."""
        state = {"next_decision": WorkflowDecision.ESCALATE}
        assert pre_implementation_router(state) == "human_escalation"


class TestBuildVerificationRouter:
    """Tests for build_verification_router."""

    def test_continue_routes_to_review(self):
        """Test continue decision routes to cursor_review."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert build_verification_router(state) == "cursor_review"

    def test_retry_routes_to_implementation(self):
        """Test retry decision routes to implementation."""
        state = {"next_decision": WorkflowDecision.RETRY}
        assert build_verification_router(state) == "implementation"


class TestCoverageCheckRouter:
    """Tests for coverage_check_router."""

    def test_continue_routes_to_security_scan(self):
        """Test continue decision routes to security_scan."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert coverage_check_router(state) == "security_scan"

    def test_retry_routes_to_implementation(self):
        """Test retry decision routes to implementation."""
        state = {"next_decision": WorkflowDecision.RETRY}
        assert coverage_check_router(state) == "implementation"


class TestSecurityScanRouter:
    """Tests for security_scan_router."""

    def test_continue_routes_to_completion(self):
        """Test continue decision routes to completion."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert security_scan_router(state) == "completion"

    def test_retry_routes_to_implementation(self):
        """Test retry decision routes to implementation."""
        state = {"next_decision": WorkflowDecision.RETRY}
        assert security_scan_router(state) == "implementation"


class TestApprovalGateRouter:
    """Tests for approval_gate_router."""

    def test_continue_routes_to_pre_implementation(self):
        """Test continue decision routes to pre_implementation."""
        state = {"next_decision": WorkflowDecision.CONTINUE}
        assert approval_gate_router(state) == "pre_implementation"

    def test_retry_routes_to_planning(self):
        """Test retry decision routes to planning."""
        state = {"next_decision": WorkflowDecision.RETRY}
        assert approval_gate_router(state) == "planning"


class TestDiscussRouter:
    """Tests for discuss_router."""

    def test_escalate_routes_to_human(self):
        """Test escalate decision routes to human_escalation."""
        state = {"next_decision": WorkflowDecision.ESCALATE}
        assert discuss_router(state) == "human_escalation"

    def test_discussion_complete_flag_routes_to_complete(self):
        """Test discussion_complete flag routes to discuss_complete."""
        state = {"discussion_complete": True}
        assert discuss_router(state) == "discuss_complete"

    def test_needs_clarification_routes_to_human(self):
        """Test needs_clarification flag routes to human_escalation."""
        state = {"needs_clarification": True}
        assert discuss_router(state) == "human_escalation"

    def test_discussion_error_routes_to_retry(self):
        """Test discussion error routes to discuss_retry."""
        state = {
            "errors": [{"type": "discussion_phase_error"}],
        }
        assert discuss_router(state) == "discuss_retry"


class TestResearchRouter:
    """Tests for research_router."""

    def test_escalate_routes_to_human(self):
        """Test escalate decision routes to human_escalation."""
        state = {"next_decision": WorkflowDecision.ESCALATE}
        assert research_router(state) == "human_escalation"

    def test_research_complete_flag_routes_to_complete(self):
        """Test research_complete flag routes to research_complete."""
        state = {"research_complete": True}
        assert research_router(state) == "research_complete"

    def test_research_errors_still_routes_to_complete(self):
        """Test research errors are non-blocking, routes to research_complete."""
        state = {"research_errors": True}
        assert research_router(state) == "research_complete"

    def test_critical_error_routes_to_human(self):
        """Test critical research error routes to human_escalation."""
        state = {
            "errors": [{"type": "research_phase_error", "critical": True}],
        }
        assert research_router(state) == "human_escalation"
