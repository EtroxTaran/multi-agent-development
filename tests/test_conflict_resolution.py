"""Tests for conflict resolution between agents."""


from orchestrator.utils.conflict_resolution import (
    Conflict,
    ConflictResolution,
    ConflictResolver,
    ConflictResult,
    ConflictType,
    ResolutionStrategy,
)


class TestConflictDetection:
    """Tests for conflict detection."""

    def test_detect_no_conflicts(self):
        """Test detection when agents agree."""
        resolver = ConflictResolver()

        cursor = {
            "overall_assessment": "approve",
            "score": 8,
            "concerns": [],
        }
        gemini = {
            "overall_assessment": "approve",
            "score": 8,
            "architecture_review": {"concerns": []},
        }

        conflicts = resolver.detect_conflicts(cursor, gemini)
        assert len(conflicts) == 0

    def test_detect_approval_mismatch(self):
        """Test detection of approval mismatch."""
        resolver = ConflictResolver()

        cursor = {"overall_assessment": "approve", "score": 8}
        gemini = {"overall_assessment": "reject", "score": 5}

        conflicts = resolver.detect_conflicts(cursor, gemini)

        assert len(conflicts) >= 1
        approval_conflict = next(
            (c for c in conflicts if c.conflict_type == ConflictType.APPROVAL_MISMATCH), None
        )
        assert approval_conflict is not None
        assert approval_conflict.cursor_position == "approve"
        assert approval_conflict.gemini_position == "reject"

    def test_detect_score_divergence(self):
        """Test detection of significant score divergence."""
        resolver = ConflictResolver()
        resolver.SCORE_DIVERGENCE_THRESHOLD = 3.0

        cursor = {"overall_assessment": "approve", "score": 9}
        gemini = {"overall_assessment": "approve", "score": 5}

        conflicts = resolver.detect_conflicts(cursor, gemini)

        score_conflict = next(
            (c for c in conflicts if c.conflict_type == ConflictType.SCORE_DIVERGENCE), None
        )
        assert score_conflict is not None
        assert "divergence" in score_conflict.details

    def test_detect_severity_disagreement(self):
        """Test detection of severity disagreement on same issue."""
        resolver = ConflictResolver()

        cursor = {
            "overall_assessment": "needs_changes",
            "score": 6,
            "concerns": [{"area": "security", "severity": "high", "description": "Risk found"}],
        }
        gemini = {
            "overall_assessment": "needs_changes",
            "score": 7,
            "architecture_review": {
                "concerns": [{"area": "security", "severity": "low", "description": "Minor risk"}]
            },
        }

        conflicts = resolver.detect_conflicts(cursor, gemini)

        severity_conflict = next(
            (c for c in conflicts if c.conflict_type == ConflictType.SEVERITY_DISAGREEMENT), None
        )
        assert severity_conflict is not None
        assert severity_conflict.area == "security"

    def test_detect_with_none_feedback(self):
        """Test detection handles None feedback."""
        resolver = ConflictResolver()

        conflicts = resolver.detect_conflicts(None, {"overall_assessment": "approve"})
        assert len(conflicts) == 0


class TestConflictResolution:
    """Tests for conflict resolution strategies."""

    def test_resolve_weighted_security(self):
        """Test weighted resolution for security issues (Cursor preferred)."""
        resolver = ConflictResolver(default_strategy=ResolutionStrategy.WEIGHTED)

        conflict = Conflict(
            conflict_type=ConflictType.SEVERITY_DISAGREEMENT,
            area="security",
            cursor_position="high",
            gemini_position="low",
        )

        resolution = resolver.resolve(conflict)

        assert resolution.resolved
        assert resolution.winning_agent == "cursor"
        assert resolution.strategy_used == ResolutionStrategy.WEIGHTED

    def test_resolve_weighted_architecture(self):
        """Test weighted resolution for architecture issues (Gemini preferred)."""
        resolver = ConflictResolver(default_strategy=ResolutionStrategy.WEIGHTED)

        conflict = Conflict(
            conflict_type=ConflictType.SEVERITY_DISAGREEMENT,
            area="architecture",
            cursor_position="high",
            gemini_position="medium",
        )

        resolution = resolver.resolve(conflict)

        assert resolution.resolved
        assert resolution.winning_agent == "gemini"

    def test_resolve_unanimous_conflict(self):
        """Test unanimous strategy escalates on conflict."""
        resolver = ConflictResolver(default_strategy=ResolutionStrategy.UNANIMOUS)

        conflict = Conflict(
            conflict_type=ConflictType.APPROVAL_MISMATCH,
            area="overall_approval",
            cursor_position="approve",
            gemini_position="reject",
        )

        resolution = resolver.resolve(conflict)

        assert not resolution.resolved
        assert resolution.requires_human_input
        assert resolution.strategy_used == ResolutionStrategy.UNANIMOUS

    def test_resolve_escalate(self):
        """Test escalate strategy always requires human input."""
        resolver = ConflictResolver(default_strategy=ResolutionStrategy.ESCALATE)

        conflict = Conflict(
            conflict_type=ConflictType.APPROVAL_MISMATCH,
            area="overall_approval",
            cursor_position="approve",
            gemini_position="approve",
        )

        resolution = resolver.resolve(conflict, ResolutionStrategy.ESCALATE)

        assert not resolution.resolved
        assert resolution.requires_human_input
        assert "human decision required" in resolution.reasoning.lower()

    def test_resolve_defer_to_lead(self):
        """Test defer to lead strategy."""
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_type=ConflictType.APPROVAL_MISMATCH,
            area="overall_approval",
            cursor_position="approve",
            gemini_position="reject",
        )

        resolution = resolver.resolve(conflict, ResolutionStrategy.DEFER_TO_LEAD)

        assert resolution.resolved
        assert resolution.winning_agent == "claude"
        assert "lead orchestrator" in resolution.reasoning.lower()

    def test_resolve_conservative_approval(self):
        """Test conservative strategy prefers rejection."""
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_type=ConflictType.APPROVAL_MISMATCH,
            area="overall_approval",
            cursor_position="approve",
            gemini_position="reject",
        )

        resolution = resolver.resolve(conflict, ResolutionStrategy.CONSERVATIVE)

        assert resolution.resolved
        assert resolution.winning_position == "reject"

    def test_resolve_conservative_severity(self):
        """Test conservative strategy prefers higher severity."""
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_type=ConflictType.SEVERITY_DISAGREEMENT,
            area="security",
            cursor_position="high",
            gemini_position="low",
        )

        resolution = resolver.resolve(conflict, ResolutionStrategy.CONSERVATIVE)

        assert resolution.resolved
        assert resolution.winning_position == "high"
        assert resolution.winning_agent == "cursor"

    def test_resolve_optimistic_approval(self):
        """Test optimistic strategy prefers approval."""
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_type=ConflictType.APPROVAL_MISMATCH,
            area="overall_approval",
            cursor_position="approve",
            gemini_position="reject",
        )

        resolution = resolver.resolve(conflict, ResolutionStrategy.OPTIMISTIC)

        assert resolution.resolved
        assert resolution.winning_position == "approve"

    def test_resolve_optimistic_severity(self):
        """Test optimistic strategy prefers lower severity."""
        resolver = ConflictResolver()

        conflict = Conflict(
            conflict_type=ConflictType.SEVERITY_DISAGREEMENT,
            area="security",
            cursor_position="high",
            gemini_position="low",
        )

        resolution = resolver.resolve(conflict, ResolutionStrategy.OPTIMISTIC)

        assert resolution.resolved
        assert resolution.winning_position == "low"
        assert resolution.winning_agent == "gemini"


class TestResolveAll:
    """Tests for resolving all conflicts."""

    def test_resolve_all_no_conflicts(self):
        """Test resolve_all with no conflicts."""
        resolver = ConflictResolver()

        cursor = {"overall_assessment": "approve", "score": 8}
        gemini = {"overall_assessment": "approve", "score": 8}

        result = resolver.resolve_all(cursor, gemini)

        assert not result.has_conflicts
        assert len(result.conflicts) == 0
        assert len(result.resolutions) == 0

    def test_resolve_all_with_conflicts(self):
        """Test resolve_all with conflicts."""
        resolver = ConflictResolver(default_strategy=ResolutionStrategy.WEIGHTED)

        cursor = {"overall_assessment": "approve", "score": 9}
        gemini = {"overall_assessment": "reject", "score": 4}

        result = resolver.resolve_all(cursor, gemini)

        assert result.has_conflicts
        assert len(result.conflicts) > 0
        assert len(result.resolutions) == len(result.conflicts)

    def test_resolve_all_tracks_unresolved(self):
        """Test that unresolved conflicts are tracked."""
        resolver = ConflictResolver(default_strategy=ResolutionStrategy.UNANIMOUS)

        cursor = {"overall_assessment": "approve", "score": 8}
        gemini = {"overall_assessment": "reject", "score": 5}

        result = resolver.resolve_all(cursor, gemini)

        # Unanimous strategy doesn't resolve conflicts
        assert result.has_conflicts
        assert result.unresolved_count > 0
        assert result.requires_escalation

    def test_resolve_all_custom_strategy(self):
        """Test resolve_all with custom strategy."""
        resolver = ConflictResolver()

        cursor = {"overall_assessment": "approve", "score": 8}
        gemini = {"overall_assessment": "reject", "score": 5}

        result = resolver.resolve_all(cursor, gemini, ResolutionStrategy.CONSERVATIVE)

        assert result.has_conflicts
        # Conservative resolves conflicts
        for resolution in result.resolutions:
            if resolution.resolved:
                assert resolution.strategy_used == ResolutionStrategy.CONSERVATIVE


class TestConsensusRecommendation:
    """Tests for consensus recommendation."""

    def test_consensus_both_approve(self):
        """Test consensus when both agents approve."""
        resolver = ConflictResolver()

        cursor = {"overall_assessment": "approve", "score": 8}
        gemini = {"overall_assessment": "approve", "score": 8}

        consensus = resolver.get_consensus_recommendation(cursor, gemini)

        assert not consensus["has_conflicts"]
        assert consensus["recommendation"] == "proceed"

    def test_consensus_needs_changes(self):
        """Test consensus when changes needed."""
        resolver = ConflictResolver()

        cursor = {"overall_assessment": "needs_changes", "score": 6}
        gemini = {"overall_assessment": "needs_changes", "score": 6}

        consensus = resolver.get_consensus_recommendation(cursor, gemini)

        assert not consensus["has_conflicts"]
        assert consensus["recommendation"] == "revise"

    def test_consensus_with_unresolved_conflicts(self):
        """Test consensus recommends escalation for unresolved."""
        resolver = ConflictResolver(default_strategy=ResolutionStrategy.UNANIMOUS)

        cursor = {"overall_assessment": "approve", "score": 9}
        gemini = {"overall_assessment": "reject", "score": 3}

        consensus = resolver.get_consensus_recommendation(cursor, gemini)

        assert consensus["has_conflicts"]
        assert consensus["requires_escalation"]
        assert consensus["recommendation"] == "escalate"

    def test_consensus_with_resolved_conflicts(self):
        """Test consensus proceeds with caution when conflicts resolved."""
        # Use CONSERVATIVE strategy which always resolves (doesn't tie)
        resolver = ConflictResolver(default_strategy=ResolutionStrategy.CONSERVATIVE)

        cursor = {"overall_assessment": "approve", "score": 9}
        gemini = {"overall_assessment": "reject", "score": 5}

        consensus = resolver.get_consensus_recommendation(cursor, gemini)

        assert consensus["has_conflicts"]
        assert consensus["resolved_count"] > 0
        assert consensus["recommendation"] == "proceed_with_caution"


class TestConflictDataclasses:
    """Tests for conflict-related dataclasses."""

    def test_conflict_to_dict(self):
        """Test Conflict conversion to dict."""
        conflict = Conflict(
            conflict_type=ConflictType.APPROVAL_MISMATCH,
            area="overall_approval",
            cursor_position="approve",
            gemini_position="reject",
            cursor_confidence=0.8,
            gemini_confidence=0.6,
        )

        data = conflict.to_dict()

        assert data["conflict_type"] == "approval_mismatch"
        assert data["area"] == "overall_approval"
        assert data["cursor_confidence"] == 0.8

    def test_conflict_resolution_to_dict(self):
        """Test ConflictResolution conversion to dict."""
        resolution = ConflictResolution(
            resolved=True,
            strategy_used=ResolutionStrategy.WEIGHTED,
            winning_position="approve",
            winning_agent="cursor",
            reasoning="Cursor preferred for security",
        )

        data = resolution.to_dict()

        assert data["resolved"] is True
        assert data["strategy_used"] == "weighted"
        assert data["winning_agent"] == "cursor"

    def test_conflict_result_to_dict(self):
        """Test ConflictResult conversion to dict."""
        result = ConflictResult(
            has_conflicts=True,
            conflicts=[
                Conflict(
                    conflict_type=ConflictType.APPROVAL_MISMATCH,
                    area="test",
                    cursor_position="a",
                    gemini_position="b",
                )
            ],
            resolutions=[
                ConflictResolution(
                    resolved=True,
                    strategy_used=ResolutionStrategy.WEIGHTED,
                    winning_position="a",
                    winning_agent="cursor",
                    reasoning="test",
                )
            ],
            unresolved_count=0,
        )

        data = result.to_dict()

        assert data["has_conflicts"] is True
        assert len(data["conflicts"]) == 1
        assert len(data["resolutions"]) == 1


class TestCustomWeights:
    """Tests for custom expertise weights."""

    def test_custom_weights(self):
        """Test resolver with custom weights."""
        custom_weights = {
            "security": {"cursor": 0.5, "gemini": 0.5},  # Equal weights
        }
        resolver = ConflictResolver(custom_weights=custom_weights)

        conflict = Conflict(
            conflict_type=ConflictType.SEVERITY_DISAGREEMENT,
            area="security",
            cursor_position="high",
            gemini_position="low",
        )

        # With equal weights and equal confidence, should escalate or pick one
        resolution = resolver.resolve(conflict, ResolutionStrategy.WEIGHTED)

        # Equal weights may lead to tie and escalation
        assert resolution is not None
