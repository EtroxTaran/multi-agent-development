"""Documentation Discovery System.

Scans and reads ALL documentation from project docs/ folder to provide
comprehensive context for AI agents. Replaces PRODUCT.md with distributed
documentation support.

Design:
- Reads ALL markdown files in docs/ folder recursively
- Builds complete context from all discovered files
- No scoring/validation - trusts docs are comprehensive
- Only escalates to human if docs/ folder is missing
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DocumentCategory(str, Enum):
    """Categories of documentation."""

    PRODUCT_VISION = "product_vision"
    ARCHITECTURE = "architecture"
    REQUIREMENTS = "requirements"
    USER_STORIES = "user_stories"
    GUIDES = "guides"
    API_REFERENCE = "api_reference"
    OTHER = "other"


@dataclass
class DiscoveredDocument:
    """A single discovered document."""

    path: Path
    title: str
    category: DocumentCategory
    content: str
    sections: dict[str, str] = field(default_factory=dict)
    frontmatter: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "title": self.title,
            "category": self.category.value,
            "content": self.content,
            "sections": self.sections,
            "frontmatter": self.frontmatter,
        }


@dataclass
class DiscoveredDocumentation:
    """Aggregated documentation from discovery."""

    documents: list[DiscoveredDocument] = field(default_factory=list)
    product_vision: Optional[str] = None
    architecture_summary: Optional[str] = None
    requirements: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    tech_stack_hints: list[str] = field(default_factory=list)
    source_folders: list[str] = field(default_factory=list)
    score: float = 0.0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "documents": [d.to_dict() for d in self.documents],
            "product_vision": self.product_vision,
            "architecture_summary": self.architecture_summary,
            "requirements": self.requirements,
            "acceptance_criteria": self.acceptance_criteria,
            "tech_stack_hints": self.tech_stack_hints,
            "source_folders": self.source_folders,
            "score": self.score,
            "issues": self.issues,
        }

    @property
    def is_valid(self) -> bool:
        """Check if documentation exists (any docs found = valid)."""
        return len(self.documents) > 0


# Patterns for categorizing documents
CATEGORY_PATTERNS = {
    DocumentCategory.PRODUCT_VISION: [
        r"product[_-]?vision",
        r"overview",
        r"executive[_-]?summary",
        r"product/readme",
        r"product/overview",
    ],
    DocumentCategory.ARCHITECTURE: [
        r"architect",
        r"design",
        r"arc42",
        r"system[_-]?overview",
        r"design/",
    ],
    DocumentCategory.REQUIREMENTS: [
        r"requirement",
        r"spec",
        r"feature",
        r"acceptance",
    ],
    DocumentCategory.USER_STORIES: [
        r"user[_-]?stor",
        r"epic",
        r"backlog",
    ],
    DocumentCategory.GUIDES: [
        r"guide",
        r"getting[_-]?started",
        r"quick[_-]?start",
        r"tutorial",
        r"how[_-]?to",
    ],
    DocumentCategory.API_REFERENCE: [
        r"api",
        r"reference",
        r"endpoint",
    ],
}

# Patterns for extracting content
ACCEPTANCE_CRITERIA_PATTERNS = [
    r"^\s*-\s*\[[ x]\]\s*(.+)$",  # Checkbox format
    r"^\s*\*\s*\[[ x]\]\s*(.+)$",  # Asterisk checkbox
    r"^\s*\d+\.\s*\[[ x]\]\s*(.+)$",  # Numbered checkbox
]

REQUIREMENT_SECTION_PATTERNS = [
    r"#+\s*(?:Requirements?|Acceptance Criteria|Goals|Objectives)",
    r"#+\s*(?:Functional Requirements?|Non-Functional Requirements?)",
]


class DocumentationScanner:
    """Scans project directories for documentation."""

    # Folders to search for documentation (case-insensitive - check both)
    DISCOVERY_PATHS = ["docs", "Docs", "DOCS"]

    # Maximum depth to search
    MAX_DEPTH = 4

    # File extensions to consider
    SUPPORTED_EXTENSIONS = [".md", ".markdown", ".txt", ".rst"]

    def __init__(
        self,
        custom_paths: Optional[list[str]] = None,
        max_depth: int = MAX_DEPTH,
    ):
        """Initialize the scanner.

        Args:
            custom_paths: Custom paths to search (in addition to defaults)
            max_depth: Maximum directory depth to search
        """
        self.discovery_paths = list(self.DISCOVERY_PATHS)
        if custom_paths:
            self.discovery_paths = custom_paths + self.discovery_paths
        self.max_depth = max_depth

    def discover(self, project_dir: Path) -> DiscoveredDocumentation:
        """Discover all documentation in the project.

        Args:
            project_dir: Path to the project directory

        Returns:
            DiscoveredDocumentation with all found docs
        """
        project_dir = Path(project_dir)
        result = DiscoveredDocumentation()

        # Find documentation folders
        doc_folders = self._find_doc_folders(project_dir)

        if not doc_folders:
            # No documentation folder found
            result.issues.append(
                "No docs/ folder found. Please create a docs/ folder with your project documentation."
            )
            result.score = 0.0
            return result

        result.source_folders = [str(f.relative_to(project_dir)) for f in doc_folders]
        logger.info(f"Found documentation folders: {result.source_folders}")

        # Scan all documentation files
        for folder in doc_folders:
            self._scan_folder(folder, project_dir, result)

        # Extract consolidated information
        self._consolidate_documentation(result)

        # Calculate score
        result.score = self._calculate_score(result)

        return result

    def _find_doc_folders(self, project_dir: Path) -> list[Path]:
        """Find documentation folders in the project.

        Args:
            project_dir: Project directory

        Returns:
            List of found documentation folders
        """
        found = []
        for path_name in self.discovery_paths:
            doc_path = project_dir / path_name
            if doc_path.exists() and doc_path.is_dir():
                found.append(doc_path)

        return found

    def _scan_folder(
        self,
        folder: Path,
        project_dir: Path,
        result: DiscoveredDocumentation,
        depth: int = 0,
    ) -> None:
        """Recursively scan a folder for documentation files.

        Args:
            folder: Folder to scan
            project_dir: Root project directory
            result: DiscoveredDocumentation to populate
            depth: Current recursion depth
        """
        if depth > self.max_depth:
            return

        try:
            for item in sorted(folder.iterdir()):
                if item.name.startswith("."):
                    continue

                if item.is_dir():
                    self._scan_folder(item, project_dir, result, depth + 1)
                elif item.is_file() and item.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    doc = self._parse_document(item, project_dir)
                    if doc:
                        result.documents.append(doc)
        except PermissionError:
            logger.warning(f"Permission denied: {folder}")

    def _parse_document(
        self,
        file_path: Path,
        project_dir: Path,
    ) -> Optional[DiscoveredDocument]:
        """Parse a single documentation file.

        Args:
            file_path: Path to the file
            project_dir: Root project directory

        Returns:
            DiscoveredDocument or None if parsing fails
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return None

        # Extract frontmatter if present
        frontmatter, content_body = self._extract_frontmatter(content)

        # Extract title from first heading or filename
        title = self._extract_title(content_body, file_path)

        # Categorize the document
        category = self._categorize_document(file_path, content_body)

        # Extract sections
        sections = self._extract_sections(content_body)

        return DiscoveredDocument(
            path=file_path.relative_to(project_dir),
            title=title,
            category=category,
            content=content_body,
            sections=sections,
            frontmatter=frontmatter,
        )

    def _extract_frontmatter(self, content: str) -> tuple[dict, str]:
        """Extract YAML frontmatter from markdown content.

        Args:
            content: Full file content

        Returns:
            Tuple of (frontmatter dict, remaining content)
        """
        if not content.startswith("---"):
            return {}, content

        lines = content.split("\n")
        frontmatter_lines = []
        content_start = 0

        in_frontmatter = False
        for i, line in enumerate(lines):
            if i == 0 and line.strip() == "---":
                in_frontmatter = True
                continue
            if in_frontmatter:
                if line.strip() == "---":
                    content_start = i + 1
                    break
                frontmatter_lines.append(line)

        if not frontmatter_lines:
            return {}, content

        # Simple YAML parsing (key: value)
        frontmatter = {}
        for line in frontmatter_lines:
            if ":" in line:
                key, value = line.split(":", 1)
                frontmatter[key.strip()] = value.strip()

        remaining_content = "\n".join(lines[content_start:])
        return frontmatter, remaining_content

    def _extract_title(self, content: str, file_path: Path) -> str:
        """Extract title from content or filename.

        Args:
            content: Document content
            file_path: File path

        Returns:
            Document title
        """
        # Look for first heading
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            return match.group(1).strip()

        # Fallback to filename
        return file_path.stem.replace("-", " ").replace("_", " ").title()

    def _categorize_document(self, file_path: Path, content: str) -> DocumentCategory:
        """Categorize a document based on path and content.

        Args:
            file_path: File path
            content: Document content

        Returns:
            DocumentCategory
        """
        path_str = str(file_path).lower()

        for category, patterns in CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, path_str, re.IGNORECASE):
                    return category

        # Check content for category hints
        content_lower = content.lower()[:500]  # Only check first 500 chars
        for category, patterns in CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    return category

        return DocumentCategory.OTHER

    def _extract_sections(self, content: str) -> dict[str, str]:
        """Extract sections from markdown content.

        Args:
            content: Document content

        Returns:
            Dict of section name to content
        """
        sections = {}
        current_section = None
        current_content = []

        for line in content.split("\n"):
            heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
            if heading_match:
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()

                current_section = heading_match.group(2).strip()
                current_content = []
            else:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _consolidate_documentation(self, result: DiscoveredDocumentation) -> None:
        """Extract consolidated information from all documents.

        Args:
            result: DiscoveredDocumentation to update
        """
        # Find product vision
        for doc in result.documents:
            if doc.category == DocumentCategory.PRODUCT_VISION:
                # Use first major section as vision
                if doc.sections:
                    first_section = list(doc.sections.values())[0]
                    if not result.product_vision:
                        result.product_vision = first_section
                break

        # Find architecture summary
        for doc in result.documents:
            if doc.category == DocumentCategory.ARCHITECTURE:
                # Look for overview/summary section
                for section_name, content in doc.sections.items():
                    if any(kw in section_name.lower() for kw in ["overview", "summary", "context"]):
                        if not result.architecture_summary:
                            result.architecture_summary = content
                        break
                break

        # Extract requirements and acceptance criteria
        for doc in result.documents:
            if doc.category in [
                DocumentCategory.REQUIREMENTS,
                DocumentCategory.PRODUCT_VISION,
            ]:
                for section_name, content in doc.sections.items():
                    # Check for requirement patterns
                    for pattern in ACCEPTANCE_CRITERIA_PATTERNS:
                        matches = re.findall(pattern, content, re.MULTILINE)
                        result.acceptance_criteria.extend(matches)

        # Deduplicate
        result.acceptance_criteria = list(set(result.acceptance_criteria))
        result.requirements = list(set(result.requirements))

    def _calculate_score(self, result: DiscoveredDocumentation) -> float:
        """Calculate documentation completeness score.

        Args:
            result: DiscoveredDocumentation

        Returns:
            Score from 0-10
        """
        score = 0.0

        # Has documents (up to 2 points)
        doc_count = len(result.documents)
        score += min(doc_count * 0.5, 2.0)

        # Has product vision (2 points)
        if result.product_vision:
            score += 2.0

        # Has architecture (2 points)
        if result.architecture_summary:
            score += 2.0

        # Has acceptance criteria (2 points)
        if len(result.acceptance_criteria) >= 3:
            score += 2.0
        elif len(result.acceptance_criteria) >= 1:
            score += 1.0

        # Has multiple categories (2 points)
        categories = set(d.category for d in result.documents)
        if len(categories) >= 3:
            score += 2.0
        elif len(categories) >= 2:
            score += 1.0

        return min(score, 10.0)

    def _parse_product_md(self, product_md: Path) -> DiscoveredDocumentation:
        """Parse legacy PRODUCT.md file.

        Args:
            product_md: Path to PRODUCT.md

        Returns:
            DiscoveredDocumentation
        """
        result = DiscoveredDocumentation()
        result.source_folders = ["PRODUCT.md (legacy)"]

        try:
            content = product_md.read_text(encoding="utf-8")
        except Exception as e:
            result.issues.append(f"Could not read PRODUCT.md: {e}")
            return result

        # Create a single document
        doc = DiscoveredDocument(
            path=Path("PRODUCT.md"),
            title=self._extract_title(content, product_md),
            category=DocumentCategory.PRODUCT_VISION,
            content=content,
            sections=self._extract_sections(content),
        )
        result.documents.append(doc)

        # Extract content
        self._consolidate_documentation(result)
        result.score = self._calculate_score(result)

        return result


def discover_documentation(
    project_dir: str | Path,
    custom_paths: Optional[list[str]] = None,
) -> DiscoveredDocumentation:
    """Convenience function to discover documentation.

    Args:
        project_dir: Path to project directory
        custom_paths: Optional custom paths to search

    Returns:
        DiscoveredDocumentation
    """
    scanner = DocumentationScanner(custom_paths=custom_paths)
    return scanner.discover(Path(project_dir))
