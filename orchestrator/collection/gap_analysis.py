"""Gap analysis engine for project requirements.

Analyzes project documentation to extract requirements and
compares against the collection to find matching items and gaps.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import CollectionItem, GapAnalysisResult, GapItem, ProjectRequirements
from .service import CollectionService

logger = logging.getLogger(__name__)

# Common technology keywords to detect
TECHNOLOGY_KEYWORDS = {
    # Languages
    "python": ["python", "py", "pip", "poetry", "uv", "pytest", "mypy", "ruff"],
    "typescript": ["typescript", "ts", "tsx", "tsc"],
    "javascript": ["javascript", "js", "jsx", "node", "npm", "yarn", "pnpm"],
    # Frameworks
    "react": ["react", "jsx", "tsx", "next.js", "nextjs", "vite"],
    "nextjs": ["next.js", "nextjs", "next"],
    "fastapi": ["fastapi", "fast-api", "uvicorn", "starlette"],
    "django": ["django"],
    "express": ["express", "expressjs"],
    "flask": ["flask"],
    # Databases
    "surrealdb": ["surrealdb", "surreal"],
    "postgres": ["postgres", "postgresql", "psycopg"],
    "mongodb": ["mongodb", "mongo", "pymongo"],
    "redis": ["redis"],
    "sqlite": ["sqlite"],
    # Tools
    "docker": ["docker", "dockerfile", "docker-compose", "containerize"],
    "kubernetes": ["kubernetes", "k8s", "kubectl", "helm"],
    "tailwind": ["tailwind", "tailwindcss"],
}

# Common feature keywords to detect
FEATURE_KEYWORDS = {
    "auth": ["auth", "authentication", "login", "signup", "oauth", "jwt", "session"],
    "api": ["api", "rest", "graphql", "endpoint", "route"],
    "database": ["database", "db", "storage", "persistence", "orm", "query"],
    "testing": ["test", "testing", "pytest", "jest", "vitest", "e2e", "unit test"],
    "deployment": ["deploy", "deployment", "ci/cd", "pipeline", "production"],
    "security": ["security", "secure", "encryption", "https", "csrf", "xss"],
    "frontend": ["frontend", "ui", "user interface", "component", "page"],
    "backend": ["backend", "server", "api", "service"],
    "fullstack": ["fullstack", "full-stack", "full stack"],
    "websocket": ["websocket", "ws", "realtime", "real-time", "socket"],
    "caching": ["cache", "caching", "redis", "memcache"],
    "logging": ["logging", "logs", "monitoring", "observability"],
    "notifications": ["notification", "email", "sms", "push"],
}


class GapAnalysisEngine:
    """Analyzes project requirements vs available collection items.

    Reads project documentation to extract requirements and
    compares against the collection to find matching items and gaps.
    """

    def __init__(self, collection_service: Optional[CollectionService] = None):
        """Initialize gap analysis engine.

        Args:
            collection_service: Optional service instance (creates new if not provided)
        """
        self.collection_service = collection_service or CollectionService()

    async def analyze_project(
        self,
        project_path: Path,
        project_name: Optional[str] = None,
    ) -> GapAnalysisResult:
        """Analyze a project and find matching items and gaps.

        Args:
            project_path: Path to the project directory
            project_name: Project name (defaults to directory name)

        Returns:
            GapAnalysisResult with matching items and gaps
        """
        project_path = Path(project_path).resolve()
        project_name = project_name or project_path.name

        # Extract requirements from project docs
        requirements = await self.extract_project_requirements(project_path, project_name)

        # Find matching items in collection
        matching_items = await self.find_matching_items(requirements)

        # Identify gaps
        gaps = await self.identify_gaps(requirements, matching_items)

        return GapAnalysisResult(
            project_name=project_name,
            requirements=requirements,
            matching_items=matching_items,
            gaps=gaps,
            analyzed_at=datetime.now(),
        )

    async def extract_project_requirements(
        self,
        project_path: Path,
        project_name: str,
    ) -> ProjectRequirements:
        """Extract requirements from project documentation.

        Reads docs/ folder, PRODUCT.md, and other documentation
        to extract technology stack and features.

        Args:
            project_path: Path to the project
            project_name: Name of the project

        Returns:
            ProjectRequirements with extracted data
        """
        technologies = set()
        features = set()
        description = ""

        # Files to scan for requirements
        doc_files = []

        # Check for docs folder (case-insensitive)
        for doc_dir_name in ["docs", "Docs", "DOCS", "Documents", "documentation"]:
            doc_dir = project_path / doc_dir_name
            if doc_dir.exists():
                doc_files.extend(doc_dir.rglob("*.md"))
                break

        # Check for common documentation files
        for doc_name in ["PRODUCT.md", "README.md", "product.md", "readme.md"]:
            doc_file = project_path / doc_name
            if doc_file.exists():
                doc_files.append(doc_file)

        # Check for package files (technology detection)
        package_files = [
            ("package.json", ["javascript", "nodejs"]),
            ("pyproject.toml", ["python"]),
            ("requirements.txt", ["python"]),
            ("Cargo.toml", ["rust"]),
            ("go.mod", ["golang"]),
            ("Dockerfile", ["docker"]),
            ("docker-compose.yml", ["docker"]),
            ("docker-compose.yaml", ["docker"]),
        ]

        for filename, techs in package_files:
            if (project_path / filename).exists():
                technologies.update(techs)

        # Scan documentation files
        for doc_file in doc_files:
            try:
                content = doc_file.read_text().lower()

                # Extract description from first paragraph of README
                if doc_file.name.lower() in ["readme.md", "product.md"]:
                    lines = doc_file.read_text().split("\n")
                    # Skip title and get first paragraph
                    in_paragraph = False
                    paragraph_lines = []
                    for line in lines:
                        if line.strip() and not line.startswith("#"):
                            in_paragraph = True
                            paragraph_lines.append(line)
                        elif in_paragraph and not line.strip():
                            break
                    if paragraph_lines:
                        description = " ".join(paragraph_lines)[:500]

                # Detect technologies
                for tech, keywords in TECHNOLOGY_KEYWORDS.items():
                    if any(kw in content for kw in keywords):
                        technologies.add(tech)

                # Detect features
                for feature, keywords in FEATURE_KEYWORDS.items():
                    if any(kw in content for kw in keywords):
                        features.add(feature)

            except Exception as e:
                logger.warning(f"Error reading {doc_file}: {e}")

        return ProjectRequirements(
            project_name=project_name,
            project_path=project_path,
            technologies=sorted(technologies),
            features=sorted(features),
            description=description,
        )

    async def find_matching_items(
        self,
        requirements: ProjectRequirements,
    ) -> list[CollectionItem]:
        """Find collection items that match project requirements.

        Args:
            requirements: Extracted project requirements

        Returns:
            List of matching CollectionItem objects
        """
        matching_items = []
        seen_ids = set()

        # Get items matching technologies
        if requirements.technologies:
            tech_items = await self.collection_service.list_items(
                technologies=requirements.technologies,
            )
            for item in tech_items:
                if item.id not in seen_ids:
                    matching_items.append(item)
                    seen_ids.add(item.id)

        # Get items matching features
        if requirements.features:
            feature_items = await self.collection_service.list_items(
                features=requirements.features,
            )
            for item in feature_items:
                if item.id not in seen_ids:
                    matching_items.append(item)
                    seen_ids.add(item.id)

        # Always include critical items
        critical_items = await self.collection_service.list_items(priority="critical")
        for item in critical_items:
            if item.id not in seen_ids:
                matching_items.append(item)
                seen_ids.add(item.id)

        # Sort by priority (critical > high > medium > low)
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        matching_items.sort(key=lambda x: priority_order.get(x.tags.priority, 2))

        return matching_items

    async def identify_gaps(
        self,
        requirements: ProjectRequirements,
        available_items: list[CollectionItem],
    ) -> list[GapItem]:
        """Find requirements not covered by available items.

        Args:
            requirements: Project requirements
            available_items: Items that match the project

        Returns:
            List of GapItem for missing coverage
        """
        gaps = []

        # Collect all technologies and features covered by available items
        covered_technologies = set()
        covered_features = set()

        for item in available_items:
            covered_technologies.update(item.tags.technology)
            covered_features.update(item.tags.feature)

        # Find uncovered technologies
        for tech in requirements.technologies:
            if tech not in covered_technologies:
                gaps.append(
                    GapItem(
                        gap_type="technology",
                        value=tech,
                        recommended_research=f"{tech} coding standards best practices",
                    )
                )

        # Find uncovered features
        for feature in requirements.features:
            if feature not in covered_features:
                gaps.append(
                    GapItem(
                        gap_type="feature",
                        value=feature,
                        recommended_research=f"{feature} implementation patterns best practices",
                    )
                )

        return gaps

    async def suggest_research_queries(
        self,
        gaps: list[GapItem],
    ) -> list[str]:
        """Generate research queries for gaps.

        Args:
            gaps: List of identified gaps

        Returns:
            List of search queries for Perplexity or other research tools
        """
        queries = []

        for gap in gaps:
            if gap.gap_type == "technology":
                queries.append(f"{gap.value} coding standards and best practices for AI agents")
                queries.append(f"{gap.value} security guardrails and common pitfalls")
            elif gap.gap_type == "feature":
                queries.append(f"{gap.value} implementation patterns and architecture")
                queries.append(f"{gap.value} testing strategies and quality assurance")

        return queries
