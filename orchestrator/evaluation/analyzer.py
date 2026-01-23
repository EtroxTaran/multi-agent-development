"""Output analyzer for deep analysis of agent outputs.

Provides semantic, structural, token efficiency, and pattern
analysis to generate improvement insights.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class PatternType(str, Enum):
    """Types of patterns detected in outputs."""

    VERBOSITY = "verbosity"
    REPETITION = "repetition"
    MISSING_STRUCTURE = "missing_structure"
    INCOMPLETE_REASONING = "incomplete_reasoning"
    TOOL_MISUSE = "tool_misuse"
    CONTEXT_LOSS = "context_loss"
    FORMAT_ERROR = "format_error"
    HALLUCINATION = "hallucination"


@dataclass
class DetectedPattern:
    """A pattern detected in agent output."""

    pattern_type: PatternType
    description: str
    severity: str  # low, medium, high
    location: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "pattern_type": self.pattern_type.value,
            "description": self.description,
            "severity": self.severity,
            "location": self.location,
            "suggestion": self.suggestion,
        }


@dataclass
class SemanticScore:
    """Semantic analysis score."""

    completeness: float  # 0-1, how complete is the output
    accuracy: float  # 0-1, accuracy vs requirements
    coherence: float  # 0-1, logical coherence
    details: str

    def overall(self) -> float:
        return (self.completeness + self.accuracy + self.coherence) / 3


@dataclass
class StructuralScore:
    """Structural analysis score."""

    schema_adherence: float  # 0-1, matches expected schema
    format_consistency: float  # 0-1, consistent formatting
    organization: float  # 0-1, well-organized
    errors: list[str] = field(default_factory=list)

    def overall(self) -> float:
        return (self.schema_adherence + self.format_consistency + self.organization) / 3


@dataclass
class EfficiencyScore:
    """Token efficiency analysis score."""

    output_tokens: int
    estimated_minimum_tokens: int
    efficiency_ratio: float  # minimum / actual
    verbosity_indicators: list[str] = field(default_factory=list)

    def overall(self) -> float:
        return min(1.0, self.efficiency_ratio)


@dataclass
class AnalysisResult:
    """Complete analysis result."""

    output_hash: str
    semantic: SemanticScore
    structural: StructuralScore
    efficiency: EfficiencyScore
    patterns: list[DetectedPattern]
    suggestions: list[str]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "output_hash": self.output_hash,
            "semantic": {
                "completeness": self.semantic.completeness,
                "accuracy": self.semantic.accuracy,
                "coherence": self.semantic.coherence,
                "details": self.semantic.details,
                "overall": self.semantic.overall(),
            },
            "structural": {
                "schema_adherence": self.structural.schema_adherence,
                "format_consistency": self.structural.format_consistency,
                "organization": self.structural.organization,
                "errors": self.structural.errors,
                "overall": self.structural.overall(),
            },
            "efficiency": {
                "output_tokens": self.efficiency.output_tokens,
                "estimated_minimum_tokens": self.efficiency.estimated_minimum_tokens,
                "efficiency_ratio": self.efficiency.efficiency_ratio,
                "verbosity_indicators": self.efficiency.verbosity_indicators,
                "overall": self.efficiency.overall(),
            },
            "patterns": [p.to_dict() for p in self.patterns],
            "suggestions": self.suggestions,
            "timestamp": self.timestamp,
        }

    def overall_score(self) -> float:
        """Calculate overall analysis score.

        Returns:
            Score from 0-1
        """
        weights = {
            "semantic": 0.4,
            "structural": 0.3,
            "efficiency": 0.2,
            "patterns": 0.1,
        }

        # Pattern penalty: more high-severity patterns = lower score
        pattern_score = 1.0
        for pattern in self.patterns:
            if pattern.severity == "high":
                pattern_score -= 0.15
            elif pattern.severity == "medium":
                pattern_score -= 0.08
            else:
                pattern_score -= 0.03
        pattern_score = max(0.0, pattern_score)

        return (
            self.semantic.overall() * weights["semantic"]
            + self.structural.overall() * weights["structural"]
            + self.efficiency.overall() * weights["efficiency"]
            + pattern_score * weights["patterns"]
        )


class OutputAnalyzer:
    """Analyzes agent outputs for quality and improvement opportunities."""

    # Common verbosity patterns
    VERBOSITY_PATTERNS = [
        (r"\b(basically|essentially|actually|really|just|simply)\b", "filler words"),
        (r"\b(in order to)\b", "verbose phrase (use 'to')"),
        (r"\b(at this point in time)\b", "verbose phrase (use 'now')"),
        (r"\b(due to the fact that)\b", "verbose phrase (use 'because')"),
        (r"(.+?)\1{2,}", "repetitive content"),
        (r"\n{3,}", "excessive newlines"),
        (r"^\s*#+ .+\n\n^\s*#+ .+", "consecutive headings without content"),
    ]

    # Structural indicators
    STRUCTURE_PATTERNS = [
        (r"^\{[\s\S]*\}$", "valid JSON object"),
        (r"^\[[\s\S]*\]$", "valid JSON array"),
        (r"^```[\s\S]*```$", "code block"),
        (r"^#+\s+.+$", "markdown heading", re.MULTILINE),
        (r"^\d+\.\s+.+$", "numbered list", re.MULTILINE),
        (r"^[-*]\s+.+$", "bullet list", re.MULTILINE),
    ]

    def __init__(self, error_history: Optional[list[dict]] = None):
        """Initialize the analyzer.

        Args:
            error_history: Historical errors for pattern detection
        """
        self.error_history = error_history or []

    def analyze(
        self,
        output: str,
        requirements: Optional[list[str]] = None,
        expected_schema: Optional[dict] = None,
        expected_format: Optional[str] = None,
    ) -> AnalysisResult:
        """Perform complete analysis on an output.

        Args:
            output: Agent output to analyze
            requirements: Expected requirements
            expected_schema: JSON schema for validation
            expected_format: Expected format (json, markdown, text)

        Returns:
            AnalysisResult with all scores and patterns
        """
        # Semantic analysis
        semantic = self._analyze_semantic(output, requirements)

        # Structural analysis
        structural = self._analyze_structure(output, expected_schema, expected_format)

        # Efficiency analysis
        efficiency = self._analyze_efficiency(output)

        # Pattern detection
        patterns = self._detect_patterns(output)

        # Generate suggestions
        suggestions = self._generate_suggestions(semantic, structural, efficiency, patterns)

        # Generate output hash
        output_hash = hashlib.sha256(output.encode()).hexdigest()[:16]

        return AnalysisResult(
            output_hash=output_hash,
            semantic=semantic,
            structural=structural,
            efficiency=efficiency,
            patterns=patterns,
            suggestions=suggestions,
        )

    def _analyze_semantic(
        self,
        output: str,
        requirements: Optional[list[str]],
    ) -> SemanticScore:
        """Analyze semantic quality of output.

        Args:
            output: Output to analyze
            requirements: Expected requirements

        Returns:
            SemanticScore
        """
        # Completeness: Check if output has substantial content
        completeness = min(1.0, len(output) / 500)  # Normalize by expected minimum

        # Accuracy: Check requirements coverage (heuristic)
        accuracy = 1.0
        if requirements:
            matched = 0
            for req in requirements:
                # Check if requirement keywords appear in output
                keywords = self._extract_keywords(req)
                if any(kw.lower() in output.lower() for kw in keywords):
                    matched += 1
            accuracy = matched / len(requirements) if requirements else 1.0

        # Coherence: Check for logical structure
        coherence = self._assess_coherence(output)

        details = f"Completeness based on length, accuracy based on {len(requirements or [])} requirements"

        return SemanticScore(
            completeness=completeness,
            accuracy=accuracy,
            coherence=coherence,
            details=details,
        )

    def _analyze_structure(
        self,
        output: str,
        expected_schema: Optional[dict],
        expected_format: Optional[str],
    ) -> StructuralScore:
        """Analyze structural quality of output.

        Args:
            output: Output to analyze
            expected_schema: JSON schema
            expected_format: Expected format

        Returns:
            StructuralScore
        """
        errors = []
        schema_adherence = 1.0
        format_consistency = 1.0
        organization = 1.0

        # Check JSON schema if expected
        if expected_schema:
            try:
                parsed = json.loads(output)
                # Basic schema check (full validation requires jsonschema)
                schema_adherence = self._check_schema_basic(parsed, expected_schema)
            except json.JSONDecodeError as e:
                schema_adherence = 0.0
                errors.append(f"Invalid JSON: {e}")

        # Check format consistency
        if expected_format == "json":
            try:
                json.loads(output)
            except json.JSONDecodeError:
                format_consistency = 0.0
                errors.append("Expected JSON format but got invalid JSON")
        elif expected_format == "markdown":
            if not re.search(r"^#+\s+", output, re.MULTILINE):
                format_consistency *= 0.8
                errors.append("Expected markdown but no headings found")

        # Organization assessment
        organization = self._assess_organization(output)

        return StructuralScore(
            schema_adherence=schema_adherence,
            format_consistency=format_consistency,
            organization=organization,
            errors=errors,
        )

    def _analyze_efficiency(self, output: str) -> EfficiencyScore:
        """Analyze token efficiency of output.

        Args:
            output: Output to analyze

        Returns:
            EfficiencyScore
        """
        # Estimate token count (roughly 4 chars per token)
        output_tokens = len(output) // 4

        # Find verbosity indicators
        verbosity_indicators = []
        for pattern, description in self.VERBOSITY_PATTERNS:
            matches = re.findall(pattern, output, re.IGNORECASE | re.MULTILINE)
            if matches:
                verbosity_indicators.append(f"{description}: {len(matches)} occurrences")

        # Estimate minimum tokens (remove detected verbosity)
        clean_output = output
        for pattern, _ in self.VERBOSITY_PATTERNS[:6]:  # Only word-level patterns
            clean_output = re.sub(pattern, "", clean_output, flags=re.IGNORECASE)

        estimated_minimum = len(clean_output) // 4
        estimated_minimum = max(estimated_minimum, output_tokens // 2)  # At least half

        efficiency_ratio = estimated_minimum / output_tokens if output_tokens > 0 else 1.0

        return EfficiencyScore(
            output_tokens=output_tokens,
            estimated_minimum_tokens=estimated_minimum,
            efficiency_ratio=efficiency_ratio,
            verbosity_indicators=verbosity_indicators,
        )

    def _detect_patterns(self, output: str) -> list[DetectedPattern]:
        """Detect problematic patterns in output.

        Args:
            output: Output to analyze

        Returns:
            List of detected patterns
        """
        patterns = []

        # Check for verbosity patterns
        for pattern, description in self.VERBOSITY_PATTERNS:
            matches = re.findall(pattern, output, re.IGNORECASE | re.MULTILINE)
            if len(matches) > 3:  # Threshold for flagging
                patterns.append(
                    DetectedPattern(
                        pattern_type=PatternType.VERBOSITY,
                        description=f"Excessive {description}",
                        severity="medium" if len(matches) > 5 else "low",
                        suggestion=f"Reduce usage of {description}",
                    )
                )

        # Check for repetition
        sentences = re.split(r"[.!?]+", output)
        unique_sentences = set(s.strip().lower() for s in sentences if len(s.strip()) > 20)
        if len(sentences) > 5 and len(unique_sentences) < len(sentences) * 0.7:
            patterns.append(
                DetectedPattern(
                    pattern_type=PatternType.REPETITION,
                    description="Significant content repetition detected",
                    severity="high",
                    suggestion="Remove duplicate content and consolidate ideas",
                )
            )

        # Check for missing structure in long outputs
        if len(output) > 2000:
            has_headings = bool(re.search(r"^#+\s+", output, re.MULTILINE))
            has_lists = bool(re.search(r"^[-*\d]+[.)\s]", output, re.MULTILINE))
            if not has_headings and not has_lists:
                patterns.append(
                    DetectedPattern(
                        pattern_type=PatternType.MISSING_STRUCTURE,
                        description="Long output lacks organizational structure",
                        severity="medium",
                        suggestion="Add headings or bullet points to organize content",
                    )
                )

        # Check for incomplete reasoning
        reasoning_starters = ["because", "therefore", "thus", "since", "due to"]
        has_reasoning = any(word in output.lower() for word in reasoning_starters)
        if len(output) > 500 and not has_reasoning:
            patterns.append(
                DetectedPattern(
                    pattern_type=PatternType.INCOMPLETE_REASONING,
                    description="Output lacks explicit reasoning",
                    severity="low",
                    suggestion="Add explanations for decisions and conclusions",
                )
            )

        # Check for format errors
        if output.count("```") % 2 != 0:
            patterns.append(
                DetectedPattern(
                    pattern_type=PatternType.FORMAT_ERROR,
                    description="Unclosed code block",
                    severity="medium",
                    location="Code blocks",
                    suggestion="Ensure all code blocks are properly closed",
                )
            )

        return patterns

    def _generate_suggestions(
        self,
        semantic: SemanticScore,
        structural: StructuralScore,
        efficiency: EfficiencyScore,
        patterns: list[DetectedPattern],
    ) -> list[str]:
        """Generate improvement suggestions.

        Args:
            semantic: Semantic analysis result
            structural: Structural analysis result
            efficiency: Efficiency analysis result
            patterns: Detected patterns

        Returns:
            List of suggestions
        """
        suggestions = []

        # Semantic suggestions
        if semantic.completeness < 0.5:
            suggestions.append("Output seems incomplete - ensure all requirements are addressed")
        if semantic.accuracy < 0.7:
            suggestions.append("Output may not fully address requirements - review coverage")
        if semantic.coherence < 0.6:
            suggestions.append("Improve logical flow and coherence between sections")

        # Structural suggestions
        if structural.schema_adherence < 0.8:
            suggestions.append("Output doesn't match expected schema - review structure")
        if structural.format_consistency < 0.8:
            suggestions.append("Inconsistent formatting detected - standardize format")
        for error in structural.errors[:3]:  # Limit to top 3
            suggestions.append(f"Fix structural issue: {error}")

        # Efficiency suggestions
        if efficiency.efficiency_ratio < 0.6:
            suggestions.append("Output is verbose - reduce filler words and repetition")
        for indicator in efficiency.verbosity_indicators[:2]:  # Limit to top 2
            suggestions.append(f"Reduce verbosity: {indicator}")

        # Pattern-based suggestions
        for pattern in patterns:
            if pattern.suggestion:
                suggestions.append(pattern.suggestion)

        # Deduplicate and limit
        seen = set()
        unique_suggestions = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique_suggestions.append(s)

        return unique_suggestions[:10]  # Limit to 10 suggestions

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text.

        Args:
            text: Text to extract from

        Returns:
            List of keywords
        """
        # Remove common words and extract significant terms
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "and",
            "but",
            "or",
            "not",
            "this",
            "that",
            "these",
            "those",
            "it",
        }

        words = re.findall(r"\b\w{3,}\b", text.lower())
        return [w for w in words if w not in stopwords][:10]

    def _assess_coherence(self, output: str) -> float:
        """Assess logical coherence of output.

        Args:
            output: Output to assess

        Returns:
            Coherence score 0-1
        """
        score = 1.0

        # Check for logical connectors
        connectors = [
            "therefore",
            "however",
            "moreover",
            "furthermore",
            "because",
            "since",
            "although",
            "while",
            "thus",
            "consequently",
            "additionally",
            "finally",
            "first",
            "second",
            "third",
            "next",
            "then",
        ]
        connector_count = sum(1 for c in connectors if c in output.lower())

        # Long output should have connectors
        if len(output) > 1000 and connector_count < 2:
            score -= 0.2

        # Check for contradictions (simple heuristic)
        contradiction_pairs = [
            ("always", "never"),
            ("all", "none"),
            ("true", "false"),
            ("yes", "no"),
        ]
        for word1, word2 in contradiction_pairs:
            if word1 in output.lower() and word2 in output.lower():
                # Might be intentional comparison, small penalty
                score -= 0.05

        return max(0.0, min(1.0, score))

    def _assess_organization(self, output: str) -> float:
        """Assess organization of output.

        Args:
            output: Output to assess

        Returns:
            Organization score 0-1
        """
        score = 0.5  # Start at middle

        # Check for headings
        heading_count = len(re.findall(r"^#+\s+", output, re.MULTILINE))
        if heading_count > 0:
            score += 0.2

        # Check for lists
        list_count = len(re.findall(r"^[-*\d]+[.)\s]", output, re.MULTILINE))
        if list_count > 0:
            score += 0.15

        # Check for code blocks
        code_block_count = output.count("```")
        if code_block_count >= 2:  # At least one complete block
            score += 0.1

        # Penalize if very long with no structure
        if len(output) > 3000 and heading_count == 0 and list_count == 0:
            score -= 0.3

        return max(0.0, min(1.0, score))

    def _check_schema_basic(self, data: Any, schema: dict) -> float:
        """Basic schema compliance check.

        Args:
            data: Parsed data
            schema: Expected schema

        Returns:
            Compliance score 0-1
        """
        if not isinstance(schema, dict):
            return 1.0

        required = schema.get("required", [])
        properties = schema.get("properties", {})

        if not isinstance(data, dict):
            return 0.0 if properties else 1.0

        # Check required fields
        if required:
            present = sum(1 for r in required if r in data)
            return present / len(required)

        # Check property presence
        if properties:
            present = sum(1 for p in properties if p in data)
            return present / len(properties)

        return 1.0
