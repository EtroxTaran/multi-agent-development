"""Validation utilities for input and feedback schemas."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class ValidationResult:
    """Result of a validation check."""

    valid: bool
    errors: list[str]
    warnings: list[str]

    def __bool__(self) -> bool:
        return self.valid


class ProductSpecValidator:
    """Validates PRODUCT.md content structure.

    Ensures the product specification contains required sections
    and meets minimum content requirements.
    """

    REQUIRED_SECTIONS = ["## Feature", "## Goals"]
    RECOMMENDED_SECTIONS = ["## Constraints", "## Success Criteria"]
    MIN_CONTENT_LENGTH = 100  # Minimum characters
    MAX_CONTENT_LENGTH = 100_000  # Maximum characters

    def validate(self, content: str) -> ValidationResult:
        """Validate PRODUCT.md content.

        Args:
            content: The raw content of PRODUCT.md

        Returns:
            ValidationResult with errors and warnings
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Check for empty content
        if not content or not content.strip():
            errors.append("PRODUCT.md is empty")
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        stripped_content = content.strip()

        # Check content length
        if len(stripped_content) < self.MIN_CONTENT_LENGTH:
            errors.append(
                f"PRODUCT.md is too short ({len(stripped_content)} chars, "
                f"min {self.MIN_CONTENT_LENGTH})"
            )

        if len(stripped_content) > self.MAX_CONTENT_LENGTH:
            errors.append(
                f"PRODUCT.md is too large ({len(stripped_content)} chars, "
                f"max {self.MAX_CONTENT_LENGTH})"
            )

        # Check for required sections (case-insensitive)
        content_lower = content.lower()
        for section in self.REQUIRED_SECTIONS:
            if section.lower() not in content_lower:
                errors.append(f"Missing required section: {section}")

        # Check for recommended sections
        for section in self.RECOMMENDED_SECTIONS:
            if section.lower() not in content_lower:
                warnings.append(f"Missing recommended section: {section}")

        # Check for at least some structured content
        if not re.search(r"^##?\s+\w", content, re.MULTILINE):
            warnings.append("No markdown headings found - consider structuring with ## headers")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


class AssessmentType(str, Enum):
    """Overall assessment types from agent feedback."""

    APPROVED = "approved"
    APPROVE = "approve"
    REVISION = "revision"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value):
        """Handle missing values by returning UNKNOWN."""
        if isinstance(value, str):
            # Try case-insensitive matching
            value_lower = value.lower()
            for member in cls:
                if member.value == value_lower:
                    return member
        return cls.UNKNOWN


@dataclass
class FeedbackItem:
    """A single feedback item from an agent."""

    category: str
    severity: str = "info"
    message: str = ""
    suggestion: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "FeedbackItem":
        """Create from dictionary."""
        return cls(
            category=data.get("category", "general"),
            severity=data.get("severity", "info"),
            message=data.get("message", data.get("description", "")),
            suggestion=data.get("suggestion", data.get("recommendation")),
        )


@dataclass
class AgentFeedbackSchema:
    """Validated feedback schema from agents.

    Provides structured validation for agent feedback, normalizing
    different field names and ensuring consistent output.
    """

    reviewer: str
    overall_assessment: AssessmentType
    score: float
    summary: Optional[str] = None
    items: list[FeedbackItem] = None
    blockers: list[str] = None
    warnings: list[str] = None

    def __post_init__(self):
        """Normalize values after initialization."""
        # Ensure score is in valid range
        self.score = max(0.0, min(10.0, round(self.score, 1)))

        # Initialize lists
        if self.items is None:
            self.items = []
        if self.blockers is None:
            self.blockers = []
        if self.warnings is None:
            self.warnings = []

        # Normalize assessment type
        if isinstance(self.overall_assessment, str):
            self.overall_assessment = AssessmentType(self.overall_assessment)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentFeedbackSchema":
        """Create from dictionary with flexible field mapping.

        Handles various field name conventions that different agents might use.
        """
        # Handle assessment field variations
        assessment = data.get("overall_assessment") or data.get("assessment") or "unknown"

        # Handle score field variations
        score = data.get("score") or data.get("rating") or data.get("confidence") or 0

        # Handle items/concerns/issues field variations
        items_data = data.get("items") or data.get("concerns") or data.get("issues") or []
        items = [
            FeedbackItem.from_dict(item)
            if isinstance(item, dict)
            else FeedbackItem(category="general", message=str(item))
            for item in items_data
        ]

        # Handle blockers field variations
        blockers = data.get("blockers") or data.get("blocking_issues") or []
        if isinstance(blockers, list):
            blockers = [str(b) if not isinstance(b, str) else b for b in blockers]

        # Handle warnings field variations
        warnings = data.get("warnings") or data.get("non_blocking_issues") or []
        if isinstance(warnings, list):
            warnings = [str(w) if not isinstance(w, str) else w for w in warnings]

        return cls(
            reviewer=data.get("reviewer", "unknown"),
            overall_assessment=AssessmentType(assessment),
            score=float(score) if score else 0.0,
            summary=data.get("summary") or data.get("description"),
            items=items,
            blockers=blockers,
            warnings=warnings,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "reviewer": self.reviewer,
            "overall_assessment": self.overall_assessment.value,
            "score": self.score,
            "summary": self.summary,
            "items": [
                {
                    "category": item.category,
                    "severity": item.severity,
                    "message": item.message,
                    "suggestion": item.suggestion,
                }
                for item in self.items
            ],
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


def validate_feedback(agent: str, raw_output: Optional[dict]) -> Optional[dict]:
    """Process and validate agent feedback.

    Args:
        agent: Name of the agent (cursor, gemini)
        raw_output: Raw parsed output from agent

    Returns:
        Validated and normalized feedback dictionary, or minimal feedback on failure
    """
    if raw_output:
        try:
            feedback = AgentFeedbackSchema.from_dict(raw_output)
            # Override reviewer with the actual agent name
            feedback.reviewer = agent
            return feedback.to_dict()
        except Exception:
            pass

    # Return minimal valid feedback on failure
    return AgentFeedbackSchema(
        reviewer=agent,
        overall_assessment=AssessmentType.UNKNOWN,
        score=0,
        summary="Failed to get feedback",
    ).to_dict()
