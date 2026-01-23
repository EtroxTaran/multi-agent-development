"""Tests for the agent evaluation system."""


from orchestrator.evaluation.analyzer import (
    AnalysisResult,
    EfficiencyScore,
    OutputAnalyzer,
    PatternType,
    SemanticScore,
    StructuralScore,
)
from orchestrator.evaluation.evaluator import EvaluationResult
from orchestrator.evaluation.g_eval import CriterionEvaluation, GEvalEvaluator, GEvalResult
from orchestrator.evaluation.metrics import (
    DEFAULT_THRESHOLDS,
    EVALUATION_CRITERIA,
    EvaluationMetric,
    MetricWeight,
    ScoreThresholds,
    compute_weighted_score,
    validate_scores,
)


class TestMetrics:
    """Tests for evaluation metrics."""

    def test_evaluation_criteria_complete(self):
        """All evaluation metrics should have criteria defined."""
        for metric in EvaluationMetric:
            assert metric in EVALUATION_CRITERIA
            weight_config = EVALUATION_CRITERIA[metric]
            assert isinstance(weight_config, MetricWeight)
            assert 0 <= weight_config.weight <= 1
            assert weight_config.description
            assert weight_config.rubric

    def test_weights_sum_to_one(self):
        """Total weights should sum to 1.0."""
        total = sum(c.weight for c in EVALUATION_CRITERIA.values())
        assert abs(total - 1.0) < 0.01

    def test_compute_weighted_score_full(self):
        """Test weighted score computation with all metrics."""
        scores = {
            "task_completion": 8.0,
            "output_quality": 7.5,
            "token_efficiency": 6.0,
            "reasoning_quality": 8.5,
            "tool_utilization": 9.0,
            "context_retention": 7.0,
            "safety": 10.0,
        }
        result = compute_weighted_score(scores)
        # Should be a weighted average
        assert 6.0 < result < 9.0

    def test_compute_weighted_score_partial(self):
        """Test weighted score with partial metrics."""
        scores = {
            "task_completion": 8.0,
            "output_quality": 7.0,
        }
        result = compute_weighted_score(scores)
        assert result > 0

    def test_compute_weighted_score_empty(self):
        """Test weighted score with no metrics."""
        result = compute_weighted_score({})
        assert result == 0.0

    def test_validate_scores_valid(self):
        """Test validation of valid scores."""
        scores = {metric.value: 7.0 for metric in EvaluationMetric}
        is_valid, errors = validate_scores(scores)
        assert is_valid
        assert not errors

    def test_validate_scores_out_of_range(self):
        """Test validation catches out-of-range scores."""
        scores = {"task_completion": 15.0}
        is_valid, errors = validate_scores(scores)
        assert not is_valid
        assert any("outside 1-10 range" in e for e in errors)

    def test_validate_scores_missing(self):
        """Test validation catches missing metrics."""
        scores = {"task_completion": 7.0}
        is_valid, errors = validate_scores(scores)
        assert not is_valid
        assert any("Missing scores" in e for e in errors)


class TestEvaluationResult:
    """Tests for EvaluationResult."""

    def test_needs_optimization(self):
        """Test optimization threshold detection."""
        result = EvaluationResult(
            evaluation_id="test-1",
            agent="claude",
            node="implement_task",
            task_id="T1",
            session_id=None,
            scores={"task_completion": 6.0},
            overall_score=6.5,
            feedback="Test feedback",
            suggestions=["Improve X"],
            prompt_hash="abc123",
        )
        assert result.needs_optimization()

    def test_is_golden_example(self):
        """Test golden example detection."""
        result = EvaluationResult(
            evaluation_id="test-1",
            agent="claude",
            node="implement_task",
            task_id="T1",
            session_id=None,
            scores={"task_completion": 9.5},
            overall_score=9.2,
            feedback="Excellent",
            suggestions=[],
            prompt_hash="abc123",
        )
        assert result.is_golden_example()

    def test_indicates_failure(self):
        """Test failure detection."""
        result = EvaluationResult(
            evaluation_id="test-1",
            agent="claude",
            node="implement_task",
            task_id="T1",
            session_id=None,
            scores={"task_completion": 3.0},
            overall_score=4.5,
            feedback="Poor",
            suggestions=["Fix everything"],
            prompt_hash="abc123",
        )
        assert result.indicates_failure()

    def test_to_dict(self):
        """Test serialization."""
        result = EvaluationResult(
            evaluation_id="test-1",
            agent="claude",
            node="implement_task",
            task_id="T1",
            session_id="session-1",
            scores={"task_completion": 8.0},
            overall_score=8.0,
            feedback="Good",
            suggestions=["Minor improvement"],
            prompt_hash="abc123",
        )
        d = result.to_dict()
        assert d["evaluation_id"] == "test-1"
        assert d["agent"] == "claude"
        assert d["overall_score"] == 8.0

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "evaluation_id": "test-1",
            "agent": "claude",
            "node": "implement_task",
            "task_id": "T1",
            "session_id": None,
            "scores": {"task_completion": 8.0},
            "overall_score": 8.0,
            "feedback": "Good",
            "suggestions": [],
            "prompt_hash": "abc123",
        }
        result = EvaluationResult.from_dict(data)
        assert result.evaluation_id == "test-1"
        assert result.overall_score == 8.0


class TestGEvalEvaluator:
    """Tests for G-Eval evaluator."""

    def test_truncate(self):
        """Test text truncation."""
        evaluator = GEvalEvaluator()
        long_text = "a" * 5000
        truncated = evaluator._truncate(long_text, 1000)
        assert len(truncated) < 1100
        assert "truncated" in truncated

    def test_format_requirements(self):
        """Test requirements formatting."""
        evaluator = GEvalEvaluator()
        requirements = ["Req 1", "Req 2", "Req 3"]
        formatted = evaluator._format_requirements(requirements)
        assert "- Req 1" in formatted
        assert "- Req 2" in formatted

    def test_format_requirements_none(self):
        """Test formatting with no requirements."""
        evaluator = GEvalEvaluator()
        formatted = evaluator._format_requirements(None)
        assert "No specific requirements" in formatted

    def test_hash_prompt(self):
        """Test prompt hashing."""
        evaluator = GEvalEvaluator()
        hash1 = evaluator._hash_prompt("test prompt")
        hash2 = evaluator._hash_prompt("test prompt")
        hash3 = evaluator._hash_prompt("different prompt")
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 16

    def test_extract_score_from_text(self):
        """Test score extraction from unstructured text."""
        evaluator = GEvalEvaluator()

        # JSON format
        assert evaluator._extract_score_from_text('{"score": 8}') == 8.0

        # Natural language
        assert evaluator._extract_score_from_text("I give this a score: 7") == 7.0

        # Fraction format
        assert evaluator._extract_score_from_text("Rating: 9/10") == 9.0

        # No score found
        assert evaluator._extract_score_from_text("No score here") == 5.0


class TestOutputAnalyzer:
    """Tests for output analyzer."""

    def test_semantic_analysis(self):
        """Test semantic quality analysis."""
        analyzer = OutputAnalyzer()
        result = analyzer._analyze_semantic(
            output="This is a complete response addressing all requirements.",
            requirements=["complete response", "requirements"],
        )
        assert isinstance(result, SemanticScore)
        assert 0 <= result.completeness <= 1
        assert 0 <= result.accuracy <= 1
        assert 0 <= result.coherence <= 1

    def test_structural_analysis_json(self):
        """Test structural analysis with JSON."""
        analyzer = OutputAnalyzer()
        result = analyzer._analyze_structure(
            output='{"key": "value"}',
            expected_schema={"required": ["key"]},
            expected_format="json",
        )
        assert isinstance(result, StructuralScore)
        assert result.schema_adherence > 0

    def test_structural_analysis_invalid_json(self):
        """Test structural analysis with invalid JSON."""
        analyzer = OutputAnalyzer()
        result = analyzer._analyze_structure(
            output="not json",
            expected_schema=None,
            expected_format="json",
        )
        assert result.format_consistency == 0.0
        assert len(result.errors) > 0

    def test_efficiency_analysis(self):
        """Test token efficiency analysis."""
        analyzer = OutputAnalyzer()
        verbose_output = "basically " * 100 + "the answer is 42"
        result = analyzer._analyze_efficiency(verbose_output)
        assert isinstance(result, EfficiencyScore)
        assert result.efficiency_ratio < 1.0
        assert len(result.verbosity_indicators) > 0

    def test_pattern_detection_verbosity(self):
        """Test verbosity pattern detection."""
        analyzer = OutputAnalyzer()
        output = "basically basically basically basically basically the answer"
        patterns = analyzer._detect_patterns(output)
        assert any(p.pattern_type == PatternType.VERBOSITY for p in patterns)

    def test_pattern_detection_repetition(self):
        """Test repetition pattern detection."""
        analyzer = OutputAnalyzer()
        output = """This is a sentence that is repeated.
        This is a sentence that is repeated.
        This is a sentence that is repeated.
        This is a sentence that is repeated.
        This is a sentence that is repeated.
        This is another sentence that is repeated."""
        patterns = analyzer._detect_patterns(output)
        assert any(p.pattern_type == PatternType.REPETITION for p in patterns)

    def test_pattern_detection_format_error(self):
        """Test format error detection."""
        analyzer = OutputAnalyzer()
        output = "```python\nprint('hello')\n"  # Unclosed code block
        patterns = analyzer._detect_patterns(output)
        assert any(p.pattern_type == PatternType.FORMAT_ERROR for p in patterns)

    def test_full_analysis(self):
        """Test complete analysis pipeline."""
        analyzer = OutputAnalyzer()
        result = analyzer.analyze(
            output="This is a well-structured response with clear reasoning.",
            requirements=["structured", "reasoning"],
        )
        assert isinstance(result, AnalysisResult)
        assert result.output_hash
        assert isinstance(result.semantic, SemanticScore)
        assert isinstance(result.structural, StructuralScore)
        assert isinstance(result.efficiency, EfficiencyScore)
        assert isinstance(result.suggestions, list)

    def test_overall_score(self):
        """Test overall score calculation."""
        analyzer = OutputAnalyzer()
        result = analyzer.analyze(
            output="A good response.",
            requirements=["good"],
        )
        score = result.overall_score()
        assert 0 <= score <= 1

    def test_extract_keywords(self):
        """Test keyword extraction."""
        analyzer = OutputAnalyzer()
        keywords = analyzer._extract_keywords("The quick brown fox jumps over the lazy dog")
        assert "quick" in keywords
        assert "brown" in keywords
        assert "the" not in keywords  # Stopword


class TestScoreThresholds:
    """Tests for score thresholds."""

    def test_default_thresholds(self):
        """Test default threshold values."""
        assert DEFAULT_THRESHOLDS.optimization_threshold == 7.0
        assert DEFAULT_THRESHOLDS.golden_example_threshold == 9.0
        assert DEFAULT_THRESHOLDS.failure_threshold == 5.0
        assert DEFAULT_THRESHOLDS.improvement_threshold == 0.5

    def test_custom_thresholds(self):
        """Test custom threshold creation."""
        custom = ScoreThresholds(
            optimization_threshold=6.0,
            golden_example_threshold=8.5,
        )
        assert custom.optimization_threshold == 6.0
        assert custom.golden_example_threshold == 8.5


class TestCriterionEvaluation:
    """Tests for criterion evaluation."""

    def test_criterion_evaluation_creation(self):
        """Test creating criterion evaluation."""
        eval = CriterionEvaluation(
            criterion="task_completion",
            score=8.5,
            reasoning="Task was completed successfully",
            feedback="Good job",
        )
        assert eval.criterion == "task_completion"
        assert eval.score == 8.5


class TestGEvalResult:
    """Tests for G-Eval result."""

    def test_g_eval_result_creation(self):
        """Test creating G-Eval result."""
        result = GEvalResult(
            scores={"task_completion": 8.0},
            overall_score=8.0,
            evaluations=[],
            suggestions=["Improve X"],
            prompt_hash="abc123",
            evaluator_model="haiku",
        )
        assert result.overall_score == 8.0
        assert result.evaluator_model == "haiku"
