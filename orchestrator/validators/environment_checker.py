"""Environment checker for pre-implementation validation.

Verifies that the development environment has all required tools
and dependencies before starting implementation.
"""

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CheckStatus(str, Enum):
    """Status of an environment check."""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class ProjectType(str, Enum):
    """Supported project types."""

    NODE = "node"
    REACT = "react"
    NODE_API = "node-api"
    JAVA_SPRING = "java-spring"
    PYTHON = "python"
    RUST = "rust"
    GO = "go"
    UNKNOWN = "unknown"


class Complexity(str, Enum):
    """Estimated project complexity."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class CheckResult:
    """Result of a single environment check."""

    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None
    version: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "version": self.version,
        }


@dataclass
class EnvironmentCheckResult:
    """Result of all environment checks."""

    ready: bool
    project_type: ProjectType
    complexity: Complexity
    checks: list[CheckResult] = field(default_factory=list)
    test_framework: Optional[str] = None
    build_command: Optional[str] = None
    test_command: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "project_type": self.project_type.value,
            "complexity": self.complexity.value,
            "checks": [c.to_dict() for c in self.checks],
            "test_framework": self.test_framework,
            "build_command": self.build_command,
            "test_command": self.test_command,
        }


class EnvironmentChecker:
    """Checks development environment for implementation readiness."""

    # Minimum required versions
    VERSION_REQUIREMENTS = {
        "node": "18.0.0",
        "java": "17",
        "python": "3.10",
        "go": "1.21",
        "rust": "1.70",
    }

    def __init__(self, project_dir: str | Path):
        """Initialize the environment checker.

        Args:
            project_dir: Path to the project directory
        """
        self.project_dir = Path(project_dir)

    def check(self) -> EnvironmentCheckResult:
        """Run all environment checks.

        Returns:
            EnvironmentCheckResult with all check results
        """
        checks: list[CheckResult] = []

        # Detect project type
        project_type = self._detect_project_type()
        logger.info(f"Detected project type: {project_type.value}")

        # Run checks based on project type
        if project_type in (ProjectType.NODE, ProjectType.REACT, ProjectType.NODE_API):
            checks.extend(self._check_node_environment())
        elif project_type == ProjectType.JAVA_SPRING:
            checks.extend(self._check_java_environment())
        elif project_type == ProjectType.PYTHON:
            checks.extend(self._check_python_environment())
        elif project_type == ProjectType.GO:
            checks.extend(self._check_go_environment())
        elif project_type == ProjectType.RUST:
            checks.extend(self._check_rust_environment())
        else:
            checks.append(
                CheckResult(
                    name="project_type",
                    status=CheckStatus.WARNING,
                    message="Could not detect project type",
                    details="Will use generic checks",
                )
            )

        # Detect test framework
        test_framework, test_command = self._detect_test_framework(project_type)

        # Detect build command
        build_command = self._detect_build_command(project_type)

        # Estimate complexity
        complexity = self._estimate_complexity()

        # Determine if environment is ready
        failed_checks = [c for c in checks if c.status == CheckStatus.FAILED]
        ready = len(failed_checks) == 0

        return EnvironmentCheckResult(
            ready=ready,
            project_type=project_type,
            complexity=complexity,
            checks=checks,
            test_framework=test_framework,
            build_command=build_command,
            test_command=test_command,
        )

    def _detect_project_type(self) -> ProjectType:
        """Detect the type of project based on configuration files."""
        # Check for Node.js
        package_json = self.project_dir / "package.json"
        if package_json.exists():
            try:
                pkg = json.loads(package_json.read_text())
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

                if "react" in deps:
                    return ProjectType.REACT
                if "express" in deps or "fastify" in deps or "hono" in deps:
                    return ProjectType.NODE_API
                return ProjectType.NODE
            except Exception:
                return ProjectType.NODE

        # Check for Java
        if (self.project_dir / "pom.xml").exists():
            return ProjectType.JAVA_SPRING
        if (self.project_dir / "build.gradle").exists():
            return ProjectType.JAVA_SPRING
        if (self.project_dir / "build.gradle.kts").exists():
            return ProjectType.JAVA_SPRING

        # Check for Python
        if (self.project_dir / "pyproject.toml").exists():
            return ProjectType.PYTHON
        if (self.project_dir / "setup.py").exists():
            return ProjectType.PYTHON
        if (self.project_dir / "requirements.txt").exists():
            return ProjectType.PYTHON

        # Check for Rust
        if (self.project_dir / "Cargo.toml").exists():
            return ProjectType.RUST

        # Check for Go
        if (self.project_dir / "go.mod").exists():
            return ProjectType.GO

        return ProjectType.UNKNOWN

    def _check_node_environment(self) -> list[CheckResult]:
        """Check Node.js environment."""
        results: list[CheckResult] = []

        # Check Node version
        node_check = self._check_command_version(
            "node",
            "--version",
            self.VERSION_REQUIREMENTS["node"],
            r"v(\d+\.\d+\.\d+)",
        )
        results.append(node_check)

        # Check package manager
        pkg_manager = self._detect_package_manager()
        if pkg_manager:
            results.append(
                CheckResult(
                    name="package_manager",
                    status=CheckStatus.PASSED,
                    message=f"Found package manager: {pkg_manager}",
                )
            )

            # Check npm install --dry-run or pnpm install --dry-run
            dry_run_check = self._check_dry_run_install(pkg_manager)
            results.append(dry_run_check)
        else:
            results.append(
                CheckResult(
                    name="package_manager",
                    status=CheckStatus.WARNING,
                    message="No lock file found (npm, pnpm, or yarn)",
                    details="Run your package manager to install dependencies first",
                )
            )

        # Check if node_modules exists
        node_modules = self.project_dir / "node_modules"
        if node_modules.exists():
            results.append(
                CheckResult(
                    name="node_modules",
                    status=CheckStatus.PASSED,
                    message="node_modules directory exists",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="node_modules",
                    status=CheckStatus.WARNING,
                    message="node_modules not found",
                    details="Run 'npm install' or equivalent to install dependencies",
                )
            )

        return results

    def _check_java_environment(self) -> list[CheckResult]:
        """Check Java environment."""
        results: list[CheckResult] = []

        # Check Java version
        java_check = self._check_command_version(
            "java",
            "--version",
            self.VERSION_REQUIREMENTS["java"],
            r"(\d+)\.\d+",
        )
        results.append(java_check)

        # Check for Gradle
        if (self.project_dir / "gradlew").exists():
            results.append(
                CheckResult(
                    name="gradle_wrapper",
                    status=CheckStatus.PASSED,
                    message="Gradle wrapper found",
                )
            )
        elif shutil.which("gradle"):
            results.append(
                CheckResult(
                    name="gradle",
                    status=CheckStatus.PASSED,
                    message="Gradle installed",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="gradle",
                    status=CheckStatus.FAILED,
                    message="Gradle not found",
                    details="Install Gradle or add a gradlew wrapper",
                )
            )

        return results

    def _check_python_environment(self) -> list[CheckResult]:
        """Check Python environment."""
        results: list[CheckResult] = []

        # Check Python version
        python_check = self._check_command_version(
            "python3",
            "--version",
            self.VERSION_REQUIREMENTS["python"],
            r"(\d+\.\d+)",
        )
        results.append(python_check)

        # Check for virtual environment
        venv_dir = self.project_dir / ".venv"
        if venv_dir.exists():
            results.append(
                CheckResult(
                    name="virtualenv",
                    status=CheckStatus.PASSED,
                    message="Virtual environment found at .venv",
                )
            )
        elif (self.project_dir / "venv").exists():
            results.append(
                CheckResult(
                    name="virtualenv",
                    status=CheckStatus.PASSED,
                    message="Virtual environment found at venv",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="virtualenv",
                    status=CheckStatus.WARNING,
                    message="No virtual environment found",
                    details="Consider creating a venv: python3 -m venv .venv",
                )
            )

        return results

    def _check_go_environment(self) -> list[CheckResult]:
        """Check Go environment."""
        results: list[CheckResult] = []

        go_check = self._check_command_version(
            "go",
            "version",
            self.VERSION_REQUIREMENTS["go"],
            r"go(\d+\.\d+)",
        )
        results.append(go_check)

        return results

    def _check_rust_environment(self) -> list[CheckResult]:
        """Check Rust environment."""
        results: list[CheckResult] = []

        rust_check = self._check_command_version(
            "rustc",
            "--version",
            self.VERSION_REQUIREMENTS["rust"],
            r"(\d+\.\d+)",
        )
        results.append(rust_check)

        # Check for cargo
        if shutil.which("cargo"):
            results.append(
                CheckResult(
                    name="cargo",
                    status=CheckStatus.PASSED,
                    message="Cargo build tool found",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="cargo",
                    status=CheckStatus.FAILED,
                    message="Cargo not found",
                )
            )

        return results

    def _check_command_version(
        self,
        command: str,
        version_flag: str,
        min_version: str,
        version_regex: str,
    ) -> CheckResult:
        """Check if a command is available and meets version requirements.

        Args:
            command: Command to run
            version_flag: Flag to get version
            min_version: Minimum required version
            version_regex: Regex to extract version number

        Returns:
            CheckResult
        """
        if not shutil.which(command):
            return CheckResult(
                name=command,
                status=CheckStatus.FAILED,
                message=f"{command} not found",
                details=f"Install {command} >= {min_version}",
            )

        try:
            result = subprocess.run(
                [command, version_flag],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout + result.stderr
            match = re.search(version_regex, output)

            if match:
                version = match.group(1)
                if self._compare_versions(version, min_version):
                    return CheckResult(
                        name=command,
                        status=CheckStatus.PASSED,
                        message=f"{command} version {version} meets requirement >= {min_version}",
                        version=version,
                    )
                else:
                    return CheckResult(
                        name=command,
                        status=CheckStatus.FAILED,
                        message=f"{command} version {version} is below minimum {min_version}",
                        version=version,
                    )
            else:
                return CheckResult(
                    name=command,
                    status=CheckStatus.WARNING,
                    message=f"Could not parse {command} version",
                    details=output[:200],
                )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=command,
                status=CheckStatus.WARNING,
                message=f"{command} version check timed out",
            )
        except Exception as e:
            return CheckResult(
                name=command,
                status=CheckStatus.WARNING,
                message=f"Error checking {command}: {e}",
            )

    def _compare_versions(self, actual: str, minimum: str) -> bool:
        """Compare version strings.

        Args:
            actual: Actual version
            minimum: Minimum required version

        Returns:
            True if actual >= minimum
        """
        try:
            actual_parts = [int(x) for x in actual.split(".")[:3]]
            min_parts = [int(x) for x in minimum.split(".")[:3]]

            # Pad to equal length
            while len(actual_parts) < len(min_parts):
                actual_parts.append(0)
            while len(min_parts) < len(actual_parts):
                min_parts.append(0)

            return actual_parts >= min_parts
        except ValueError:
            # Can't parse, assume it passes
            return True

    def _detect_package_manager(self) -> Optional[str]:
        """Detect Node.js package manager from lock files."""
        if (self.project_dir / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (self.project_dir / "yarn.lock").exists():
            return "yarn"
        if (self.project_dir / "package-lock.json").exists():
            return "npm"
        if (self.project_dir / "bun.lockb").exists():
            return "bun"
        return None

    def _check_dry_run_install(self, pkg_manager: str) -> CheckResult:
        """Run package manager install in dry-run mode.

        Args:
            pkg_manager: Package manager name

        Returns:
            CheckResult
        """
        commands = {
            "npm": ["npm", "install", "--dry-run"],
            "pnpm": ["pnpm", "install", "--dry-run"],
            "yarn": ["yarn", "install", "--check-files"],
            "bun": ["bun", "install", "--dry-run"],
        }

        cmd = commands.get(pkg_manager)
        if not cmd:
            return CheckResult(
                name="dry_run_install",
                status=CheckStatus.SKIPPED,
                message=f"Dry run not supported for {pkg_manager}",
            )

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                return CheckResult(
                    name="dry_run_install",
                    status=CheckStatus.PASSED,
                    message="Dependency resolution successful",
                )
            else:
                return CheckResult(
                    name="dry_run_install",
                    status=CheckStatus.WARNING,
                    message="Dependency issues detected",
                    details=result.stderr[:500] if result.stderr else result.stdout[:500],
                )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name="dry_run_install",
                status=CheckStatus.WARNING,
                message="Dependency check timed out",
            )
        except Exception as e:
            return CheckResult(
                name="dry_run_install",
                status=CheckStatus.WARNING,
                message=f"Could not run dry-run install: {e}",
            )

    def _detect_test_framework(
        self, project_type: ProjectType
    ) -> tuple[Optional[str], Optional[str]]:
        """Detect the test framework used by the project.

        Returns:
            Tuple of (framework_name, test_command)
        """
        package_json = self.project_dir / "package.json"

        if project_type in (ProjectType.NODE, ProjectType.REACT, ProjectType.NODE_API):
            if package_json.exists():
                try:
                    pkg = json.loads(package_json.read_text())
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    scripts = pkg.get("scripts", {})

                    # Check test script
                    test_script = scripts.get("test", "")

                    if "vitest" in deps or "vitest" in test_script:
                        return "vitest", "npm run test"
                    if "jest" in deps or "jest" in test_script:
                        return "jest", "npm run test"
                    if "mocha" in deps:
                        return "mocha", "npm run test"
                    if "test" in scripts:
                        return "npm test", "npm run test"
                except Exception:
                    pass

        elif project_type == ProjectType.PYTHON:
            pyproject = self.project_dir / "pyproject.toml"
            if pyproject.exists():
                content = pyproject.read_text()
                if "pytest" in content:
                    return "pytest", "pytest"
            if (self.project_dir / "pytest.ini").exists():
                return "pytest", "pytest"
            if (self.project_dir / "tests").is_dir():
                return "pytest", "pytest"

        elif project_type == ProjectType.JAVA_SPRING:
            return "junit", "./gradlew test"

        elif project_type == ProjectType.RUST:
            return "cargo test", "cargo test"

        elif project_type == ProjectType.GO:
            return "go test", "go test ./..."

        return None, None

    def _detect_build_command(self, project_type: ProjectType) -> Optional[str]:
        """Detect the build command for the project."""
        if project_type in (ProjectType.NODE, ProjectType.REACT, ProjectType.NODE_API):
            package_json = self.project_dir / "package.json"
            if package_json.exists():
                try:
                    pkg = json.loads(package_json.read_text())
                    scripts = pkg.get("scripts", {})

                    if "type-check" in scripts:
                        return "npm run type-check && npm run build"
                    if "build" in scripts:
                        return "npm run build"
                except Exception:
                    pass
            return "npm run build"

        elif project_type == ProjectType.JAVA_SPRING:
            if (self.project_dir / "gradlew").exists():
                return "./gradlew build -x test"
            return "gradle build -x test"

        elif project_type == ProjectType.RUST:
            return "cargo build"

        elif project_type == ProjectType.GO:
            return "go build ./..."

        elif project_type == ProjectType.PYTHON:
            if (self.project_dir / "pyproject.toml").exists():
                return "python -m build"
            return None

        return None

    def _estimate_complexity(self) -> Complexity:
        """Estimate project complexity from PRODUCT.md.

        Returns:
            Estimated complexity level
        """
        product_file = self.project_dir / "PRODUCT.md"
        if not product_file.exists():
            return Complexity.MEDIUM

        try:
            content = product_file.read_text()

            # Count acceptance criteria / requirements
            criteria_count = len(re.findall(r"^\s*-\s*\[[ x]\]", content, re.MULTILINE))
            bullet_count = len(re.findall(r"^\s*[-*]\s+\w", content, re.MULTILINE))

            # Count technical sections
            technical_sections = len(
                re.findall(
                    r"#+\s*(API|Database|Schema|Architecture|Security|Performance)",
                    content,
                    re.IGNORECASE,
                )
            )

            # Word count as rough estimate
            word_count = len(content.split())

            # Scoring
            score = 0
            score += min(criteria_count + bullet_count, 20)
            score += technical_sections * 5
            score += word_count // 100

            if score < 15:
                return Complexity.LOW
            elif score < 40:
                return Complexity.MEDIUM
            else:
                return Complexity.HIGH

        except Exception:
            return Complexity.MEDIUM


def check_environment(project_dir: str | Path) -> EnvironmentCheckResult:
    """Convenience function to check environment.

    Args:
        project_dir: Path to the project directory

    Returns:
        EnvironmentCheckResult
    """
    checker = EnvironmentChecker(project_dir)
    return checker.check()
