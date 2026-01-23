"""Product specification (PRODUCT.md) validator.

Validates that PRODUCT.md files have complete, non-placeholder content
with required sections and proper formatting.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class IssueSeverity(str, Enum):
    """Severity levels for validation issues."""

    ERROR = "error"  # Blocks workflow
    WARNING = "warning"  # Logged but doesn't block
    INFO = "info"  # Suggestion for improvement


@dataclass
class ValidationIssue:
    """A single validation issue."""

    section: str
    message: str
    severity: IssueSeverity
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "section": self.section,
            "message": self.message,
            "severity": self.severity.value,
            "suggestion": self.suggestion,
        }


@dataclass
class ProductValidationResult:
    """Result of validating a PRODUCT.md file."""

    valid: bool
    score: float  # 0-10 scale
    issues: list[ValidationIssue] = field(default_factory=list)
    section_scores: dict[str, float] = field(default_factory=dict)
    placeholder_count: int = 0

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "score": self.score,
            "issues": [i.to_dict() for i in self.issues],
            "section_scores": self.section_scores,
            "placeholder_count": self.placeholder_count,
        }


# Placeholder patterns to detect
PLACEHOLDER_PATTERNS = [
    r"\[TODO\]",
    r"\[TBD\]",
    r"\[FIXME\]",
    r"\[INSERT.*?\]",
    r"\[ADD.*?\]",
    r"\[YOUR.*?\]",
    r"\[DESCRIBE.*?\]",
    r"Lorem ipsum",
    r"placeholder",
    r"xxx+",
    r"___+",
    r"\.\.\.",
    r"\[Feature Name Here\]",
    r"\[Brief description",
    r"\[Describe the problem\]",
    r"\[Requirements\]",
]


# Section rules: (min_chars, required, weight)
SECTION_RULES = {
    "feature_name": {
        "patterns": [r"#+\s*Feature Name", r"^#\s+\w+"],
        "min_chars": 5,
        "max_chars": 100,
        "required": True,
        "weight": 1.0,
    },
    "summary": {
        "patterns": [r"#+\s*Summary", r"#+\s*Overview"],
        "min_chars": 50,
        "max_chars": 500,
        "required": True,
        "weight": 1.5,
    },
    "problem_statement": {
        "patterns": [r"#+\s*Problem Statement", r"#+\s*Problem", r"#+\s*Background"],
        "min_chars": 100,
        "required": True,
        "weight": 1.5,
    },
    "acceptance_criteria": {
        "patterns": [r"#+\s*Acceptance Criteria", r"#+\s*Goals", r"#+\s*Requirements"],
        "min_checklist_items": 3,
        "required": True,
        "weight": 2.0,
    },
    "examples": {
        "patterns": [r"#+\s*Example", r"#+\s*API Design", r"#+\s*Data Model"],
        "min_code_blocks": 1,
        "required": True,
        "weight": 1.5,
    },
    "technical_constraints": {
        "patterns": [r"#+\s*Technical", r"#+\s*Non-Functional", r"#+\s*Performance"],
        "required": True,
        "weight": 1.0,
    },
    "testing_strategy": {
        "patterns": [r"#+\s*Testing", r"#+\s*Test Plan"],
        "required": True,
        "weight": 1.0,
    },
    "definition_of_done": {
        "patterns": [r"#+\s*Definition of Done", r"#+\s*Success Criteria", r"#+\s*Success Metrics"],
        "min_checklist_items": 3,
        "required": False,
        "weight": 0.5,
    },
}


class ProductValidator:
    """Validates PRODUCT.md specifications for completeness and quality."""

    def __init__(self, strict_mode: bool = False):
        """Initialize the validator.

        Args:
            strict_mode: If True, warnings also cause validation failure
        """
        self.strict_mode = strict_mode
        self.placeholder_regex = re.compile(
            "|".join(PLACEHOLDER_PATTERNS),
            re.IGNORECASE,
        )

    def validate(self, content: str) -> ProductValidationResult:
        """Validate PRODUCT.md content.

        Args:
            content: The markdown content to validate

        Returns:
            ProductValidationResult with score and issues
        """
        issues: list[ValidationIssue] = []
        section_scores: dict[str, float] = {}

        # Detect placeholders
        placeholder_matches = self.placeholder_regex.findall(content)
        placeholder_count = len(placeholder_matches)

        if placeholder_count > 0:
            issues.append(
                ValidationIssue(
                    section="general",
                    message=f"Found {placeholder_count} placeholder(s) in content",
                    severity=IssueSeverity.ERROR,
                    suggestion="Replace all placeholders with actual content",
                )
            )

        # Validate each section
        total_weight = 0.0
        weighted_score = 0.0

        for section_name, rules in SECTION_RULES.items():
            score, section_issues = self._validate_section(content, section_name, rules)
            section_scores[section_name] = score
            issues.extend(section_issues)

            weight = rules.get("weight", 1.0)
            total_weight += weight
            weighted_score += score * weight

        # Calculate final score
        base_score = (weighted_score / total_weight) if total_weight > 0 else 0.0

        # Penalize for placeholders (up to 3 points)
        placeholder_penalty = min(placeholder_count * 0.5, 3.0)
        final_score = max(0.0, base_score - placeholder_penalty)

        # Determine validity
        error_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
        warning_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)

        valid = error_count == 0 and (not self.strict_mode or warning_count == 0)

        # Fail if score too low
        if final_score < 4.0:
            valid = False
            if error_count == 0:
                issues.append(
                    ValidationIssue(
                        section="overall",
                        message=f"Overall score {final_score:.1f} is below minimum threshold (4.0)",
                        severity=IssueSeverity.ERROR,
                        suggestion="Add more detail to required sections",
                    )
                )

        return ProductValidationResult(
            valid=valid,
            score=round(final_score, 1),
            issues=issues,
            section_scores=section_scores,
            placeholder_count=placeholder_count,
        )

    def validate_file(self, file_path: str | Path) -> ProductValidationResult:
        """Validate a PRODUCT.md file.

        Args:
            file_path: Path to the PRODUCT.md file

        Returns:
            ProductValidationResult
        """
        path = Path(file_path)
        if not path.exists():
            return ProductValidationResult(
                valid=False,
                score=0.0,
                issues=[
                    ValidationIssue(
                        section="file",
                        message=f"File not found: {path}",
                        severity=IssueSeverity.ERROR,
                        suggestion="Create PRODUCT.md with your feature specification",
                    )
                ],
            )

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return ProductValidationResult(
                valid=False,
                score=0.0,
                issues=[
                    ValidationIssue(
                        section="file",
                        message=f"Could not read file: {e}",
                        severity=IssueSeverity.ERROR,
                    )
                ],
            )

        return self.validate(content)

    def _validate_section(
        self,
        content: str,
        section_name: str,
        rules: dict,
    ) -> tuple[float, list[ValidationIssue]]:
        """Validate a single section.

        Args:
            content: Full markdown content
            section_name: Name of the section
            rules: Validation rules for the section

        Returns:
            Tuple of (score 0-10, list of issues)
        """
        issues: list[ValidationIssue] = []

        # Find the section
        section_content = self._extract_section(content, rules.get("patterns", []))

        if section_content is None:
            if rules.get("required", False):
                issues.append(
                    ValidationIssue(
                        section=section_name,
                        message=f"Required section '{section_name}' not found",
                        severity=IssueSeverity.ERROR,
                        suggestion=f"Add a '{section_name}' section with relevant content",
                    )
                )
                return 0.0, issues
            else:
                # Optional section missing is fine
                return 5.0, issues  # Neutral score

        # Check minimum characters
        min_chars = rules.get("min_chars")
        if min_chars and len(section_content) < min_chars:
            issues.append(
                ValidationIssue(
                    section=section_name,
                    message=f"Section '{section_name}' has only {len(section_content)} chars (min: {min_chars})",
                    severity=IssueSeverity.WARNING,
                    suggestion=f"Add more detail to reach at least {min_chars} characters",
                )
            )
            # Proportional score based on content length
            char_score = (len(section_content) / min_chars) * 10
            return min(char_score, 10.0), issues

        # Check maximum characters
        max_chars = rules.get("max_chars")
        if max_chars and len(section_content) > max_chars:
            issues.append(
                ValidationIssue(
                    section=section_name,
                    message=f"Section '{section_name}' exceeds max length ({len(section_content)} > {max_chars})",
                    severity=IssueSeverity.INFO,
                    suggestion="Consider being more concise",
                )
            )

        # Check minimum checklist items
        min_checklist = rules.get("min_checklist_items")
        if min_checklist:
            checklist_count = len(re.findall(r"^\s*-\s*\[[ x]\]", section_content, re.MULTILINE))
            # Also count bullet points as potential checklist items
            bullet_count = len(re.findall(r"^\s*[-*]\s+\w", section_content, re.MULTILINE))
            total_items = max(checklist_count, bullet_count)

            if total_items < min_checklist:
                issues.append(
                    ValidationIssue(
                        section=section_name,
                        message=f"Section '{section_name}' has only {total_items} items (min: {min_checklist})",
                        severity=IssueSeverity.WARNING,
                        suggestion=f"Add at least {min_checklist} checklist items with '- [ ]' format",
                    )
                )
                return (total_items / min_checklist) * 10, issues

        # Check minimum code blocks
        min_code_blocks = rules.get("min_code_blocks")
        if min_code_blocks:
            code_block_count = len(re.findall(r"```[\s\S]*?```", section_content))
            if code_block_count < min_code_blocks:
                issues.append(
                    ValidationIssue(
                        section=section_name,
                        message=f"Section '{section_name}' has only {code_block_count} code blocks (min: {min_code_blocks})",
                        severity=IssueSeverity.WARNING,
                        suggestion="Add code examples in fenced code blocks (```)",
                    )
                )
                if code_block_count == 0:
                    return 3.0, issues  # Partial credit for having the section
                return (code_block_count / min_code_blocks) * 10, issues

        # Check for placeholders in section
        section_placeholders = self.placeholder_regex.findall(section_content)
        if section_placeholders:
            issues.append(
                ValidationIssue(
                    section=section_name,
                    message=f"Section '{section_name}' contains placeholders",
                    severity=IssueSeverity.ERROR,
                    suggestion="Replace placeholder text with actual content",
                )
            )
            return 3.0, issues  # Heavily penalize

        # Section passes all checks
        return 10.0, issues

    def _extract_section(
        self,
        content: str,
        patterns: list[str],
    ) -> Optional[str]:
        """Extract section content from markdown.

        Args:
            content: Full markdown content
            patterns: Regex patterns to match section header

        Returns:
            Section content or None if not found
        """
        for pattern in patterns:
            # Find section header
            header_match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if header_match:
                start = header_match.end()

                # Find next section header (same or higher level)
                header_level_match = re.match(r"(#+)", header_match.group())
                if header_level_match:
                    level = len(header_level_match.group(1))
                    # Look for next header of same or higher level
                    next_header = re.search(
                        rf"^#{{{1},{level}}}\s+\w",
                        content[start:],
                        re.MULTILINE,
                    )
                    if next_header:
                        end = start + next_header.start()
                    else:
                        end = len(content)
                else:
                    end = len(content)

                section_content = content[start:end].strip()
                if section_content:
                    return section_content

        return None


def validate_product_file(file_path: str | Path, strict: bool = False) -> ProductValidationResult:
    """Convenience function to validate a PRODUCT.md file.

    Args:
        file_path: Path to the file
        strict: Whether to use strict mode

    Returns:
        ProductValidationResult
    """
    validator = ProductValidator(strict_mode=strict)
    return validator.validate_file(file_path)
