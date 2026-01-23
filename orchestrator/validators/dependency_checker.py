"""Dependency checker for npm, Docker, and framework versions.

Provides strategies for checking:
- NPM package updates and vulnerabilities
- Docker image security and best practices
- Framework version compatibility
"""

import json
import logging
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DependencySeverity(Enum):
    """Severity levels for dependency issues."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class DependencyFinding:
    """A finding from dependency analysis."""

    severity: DependencySeverity
    category: str  # "npm", "docker", "framework"
    package: str
    message: str
    current_version: Optional[str] = None
    recommended_version: Optional[str] = None
    cve: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    auto_fixable: bool = False
    fix_command: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "severity": self.severity.value,
            "category": self.category,
            "package": self.package,
            "message": self.message,
            "current_version": self.current_version,
            "recommended_version": self.recommended_version,
            "cve": self.cve,
            "file": self.file,
            "line": self.line,
            "auto_fixable": self.auto_fixable,
            "fix_command": self.fix_command,
        }


@dataclass
class DependencyCheckResult:
    """Result of dependency checking."""

    passed: bool
    total_findings: int
    blocking_findings: int
    findings: list[DependencyFinding] = field(default_factory=list)
    npm_analysis: dict = field(default_factory=dict)
    docker_analysis: dict = field(default_factory=dict)
    framework_analysis: dict = field(default_factory=dict)
    recommendations: list[dict] = field(default_factory=list)
    auto_fixable: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "total_findings": self.total_findings,
            "blocking_findings": self.blocking_findings,
            "findings": [f.to_dict() for f in self.findings],
            "npm_analysis": self.npm_analysis,
            "docker_analysis": self.docker_analysis,
            "framework_analysis": self.framework_analysis,
            "recommendations": self.recommendations,
            "auto_fixable": self.auto_fixable,
        }


class DependencyStrategy(ABC):
    """Abstract base class for dependency checking strategies."""

    @abstractmethod
    def check(self, project_dir: Path) -> list[DependencyFinding]:
        """Run dependency checks.

        Args:
            project_dir: Project directory path

        Returns:
            List of findings
        """
        pass


class NpmDependencyStrategy(DependencyStrategy):
    """Strategy for checking npm dependencies."""

    def check(self, project_dir: Path) -> list[DependencyFinding]:
        """Check npm dependencies for outdated packages and vulnerabilities.

        Args:
            project_dir: Project directory path

        Returns:
            List of findings
        """
        findings = []

        # Check if package.json exists
        package_json = project_dir / "package.json"
        if not package_json.exists():
            return findings

        # Check for outdated packages
        findings.extend(self._check_outdated(project_dir))

        # Check for vulnerabilities
        findings.extend(self._check_audit(project_dir))

        return findings

    def _check_outdated(self, project_dir: Path) -> list[DependencyFinding]:
        """Check for outdated packages using npm outdated."""
        findings = []

        try:
            proc = subprocess.run(
                ["npm", "outdated", "--json"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # npm outdated returns non-zero if packages are outdated
            if proc.stdout:
                try:
                    outdated = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    return findings

                for package, info in outdated.items():
                    current = info.get("current", "")
                    wanted = info.get("wanted", "")
                    latest = info.get("latest", "")

                    # Determine update type
                    if self._is_major_update(current, latest):
                        severity = DependencySeverity.MEDIUM
                        update_type = "major"
                        auto_fixable = False
                    elif self._is_minor_update(current, latest):
                        severity = DependencySeverity.LOW
                        update_type = "minor"
                        auto_fixable = True
                    else:
                        severity = DependencySeverity.INFO
                        update_type = "patch"
                        auto_fixable = True

                    findings.append(
                        DependencyFinding(
                            severity=severity,
                            category="npm",
                            package=package,
                            message=f"Outdated ({update_type}): {current} -> {latest}",
                            current_version=current,
                            recommended_version=latest,
                            auto_fixable=auto_fixable,
                            fix_command=f"npm install {package}@{latest}" if auto_fixable else None,
                        )
                    )

        except subprocess.TimeoutExpired:
            logger.warning("npm outdated timed out")
        except FileNotFoundError:
            logger.warning("npm not found")
        except Exception as e:
            logger.warning(f"npm outdated failed: {e}")

        return findings

    def _check_audit(self, project_dir: Path) -> list[DependencyFinding]:
        """Check for vulnerabilities using npm audit."""
        findings = []

        try:
            proc = subprocess.run(
                ["npm", "audit", "--json"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if proc.stdout:
                try:
                    audit = json.loads(proc.stdout)
                except json.JSONDecodeError:
                    return findings

                vulnerabilities = audit.get("vulnerabilities", {})

                for package, vuln_info in vulnerabilities.items():
                    severity_str = vuln_info.get("severity", "info")
                    severity = self._map_severity(severity_str)

                    via = vuln_info.get("via", [])
                    # Get CVE if available
                    cve = None
                    title = "Vulnerability"
                    for v in via:
                        if isinstance(v, dict):
                            cve = (
                                v.get("cve") or v.get("url", "").split("/")[-1]
                                if "github.com/advisories" in v.get("url", "")
                                else None
                            )
                            title = v.get("title", title)
                            break

                    fix_available = vuln_info.get("fixAvailable", False)

                    findings.append(
                        DependencyFinding(
                            severity=severity,
                            category="npm",
                            package=package,
                            message=f"Security vulnerability: {title}",
                            cve=cve,
                            auto_fixable=bool(fix_available),
                            fix_command="npm audit fix" if fix_available else None,
                        )
                    )

        except subprocess.TimeoutExpired:
            logger.warning("npm audit timed out")
        except FileNotFoundError:
            logger.warning("npm not found")
        except Exception as e:
            logger.warning(f"npm audit failed: {e}")

        return findings

    def _is_major_update(self, current: str, latest: str) -> bool:
        """Check if update is a major version change."""
        try:
            current_major = current.split(".")[0].lstrip("^~")
            latest_major = latest.split(".")[0].lstrip("^~")
            return current_major != latest_major
        except Exception:
            return False

    def _is_minor_update(self, current: str, latest: str) -> bool:
        """Check if update is a minor version change."""
        try:
            current_parts = current.split(".")
            latest_parts = latest.split(".")
            if len(current_parts) >= 2 and len(latest_parts) >= 2:
                current_minor = current_parts[1]
                latest_minor = latest_parts[1]
                return current_parts[0] == latest_parts[0] and current_minor != latest_minor
        except Exception:
            return False
        return False

    def _map_severity(self, severity_str: str) -> DependencySeverity:
        """Map npm audit severity to our severity enum."""
        mapping = {
            "critical": DependencySeverity.CRITICAL,
            "high": DependencySeverity.HIGH,
            "moderate": DependencySeverity.MEDIUM,
            "low": DependencySeverity.LOW,
            "info": DependencySeverity.INFO,
        }
        return mapping.get(severity_str.lower(), DependencySeverity.INFO)


class DockerImageStrategy(DependencyStrategy):
    """Strategy for checking Docker image security."""

    # Known LTS versions for common base images
    LTS_VERSIONS = {
        "node": ["20", "22"],
        "python": ["3.11", "3.12"],
        "alpine": ["3.19", "3.20"],
        "ubuntu": ["22.04", "24.04"],
        "debian": ["bookworm", "trixie"],
    }

    def check(self, project_dir: Path) -> list[DependencyFinding]:
        """Check Docker files for security issues.

        Args:
            project_dir: Project directory path

        Returns:
            List of findings
        """
        findings = []

        # Check Dockerfile
        dockerfile = project_dir / "Dockerfile"
        if dockerfile.exists():
            findings.extend(self._check_dockerfile(dockerfile))

        # Check docker-compose files
        for compose_file in project_dir.glob("docker-compose*.y*ml"):
            findings.extend(self._check_compose(compose_file))

        # Check for .dockerignore
        if dockerfile.exists() and not (project_dir / ".dockerignore").exists():
            findings.append(
                DependencyFinding(
                    severity=DependencySeverity.MEDIUM,
                    category="docker",
                    package=".dockerignore",
                    message="Missing .dockerignore file",
                    file="project",
                )
            )

        return findings

    def _check_dockerfile(self, dockerfile: Path) -> list[DependencyFinding]:
        """Check Dockerfile for issues."""
        findings = []
        content = dockerfile.read_text()
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()

            # Check for :latest tag
            if line_stripped.startswith("FROM"):
                match = re.match(r"FROM\s+(\S+)", line_stripped)
                if match:
                    image = match.group(1)
                    if ":latest" in image or ":" not in image:
                        findings.append(
                            DependencyFinding(
                                severity=DependencySeverity.HIGH,
                                category="docker",
                                package=image,
                                message="Using :latest tag or untagged image (unpinned version)",
                                file=str(dockerfile),
                                line=i,
                            )
                        )

                    # Check for EOL base images
                    findings.extend(self._check_base_image_version(image, dockerfile, i))

            # Check for hardcoded secrets in ENV
            if line_stripped.startswith("ENV"):
                if any(
                    secret in line_stripped.lower()
                    for secret in ["password=", "secret=", "api_key=", "token="]
                ):
                    findings.append(
                        DependencyFinding(
                            severity=DependencySeverity.CRITICAL,
                            category="docker",
                            package="Dockerfile",
                            message="Potential hardcoded secret in ENV",
                            file=str(dockerfile),
                            line=i,
                        )
                    )

        return findings

    def _check_base_image_version(
        self, image: str, dockerfile: Path, line: int
    ) -> list[DependencyFinding]:
        """Check if base image version is supported."""
        findings = []

        for base, lts_versions in self.LTS_VERSIONS.items():
            if image.startswith(f"{base}:"):
                version = image.split(":")[1].split("-")[0]
                if version and version not in lts_versions and version != "latest":
                    findings.append(
                        DependencyFinding(
                            severity=DependencySeverity.MEDIUM,
                            category="docker",
                            package=image,
                            message=f"Base image version may be EOL. LTS versions: {', '.join(lts_versions)}",
                            file=str(dockerfile),
                            line=line,
                            current_version=version,
                            recommended_version=lts_versions[0] if lts_versions else None,
                        )
                    )

        return findings

    def _check_compose(self, compose_file: Path) -> list[DependencyFinding]:
        """Check docker-compose file for issues."""
        findings = []
        content = compose_file.read_text()
        lines = content.split("\n")

        for i, line in enumerate(lines, 1):
            line_stripped = line.strip()

            # Check for :latest tag in images
            if "image:" in line_stripped and (
                ":latest" in line_stripped
                or "image:" in line_stripped
                and ":" not in line_stripped.split("image:")[1]
            ):
                findings.append(
                    DependencyFinding(
                        severity=DependencySeverity.HIGH,
                        category="docker",
                        package="docker-compose",
                        message="Using :latest tag or untagged image in compose file",
                        file=str(compose_file),
                        line=i,
                    )
                )

            # Check for hardcoded secrets
            if any(
                secret in line_stripped.lower()
                for secret in ["password:", "secret:", "api_key:", "token:"]
            ):
                # Skip if it's using variable substitution
                if "${" not in line_stripped:
                    findings.append(
                        DependencyFinding(
                            severity=DependencySeverity.CRITICAL,
                            category="docker",
                            package="docker-compose",
                            message="Potential hardcoded secret in docker-compose",
                            file=str(compose_file),
                            line=i,
                        )
                    )

        return findings


class FrameworkVersionStrategy(DependencyStrategy):
    """Strategy for checking framework version compatibility."""

    # Framework compatibility matrix
    FRAMEWORK_VERSIONS = {
        "react": {
            "lts": ["18", "19"],
            "eol": ["16", "17"],
            "upgrade_guide": "https://react.dev/blog",
        },
        "next": {
            "lts": ["14", "15"],
            "eol": ["12", "13"],
            "upgrade_guide": "https://nextjs.org/docs/upgrading",
        },
        "@nestjs/core": {
            "lts": ["10"],
            "eol": ["8", "9"],
            "upgrade_guide": "https://docs.nestjs.com/migration-guide",
        },
        "typescript": {
            "lts": ["5"],
            "eol": ["4"],
            "upgrade_guide": "https://www.typescriptlang.org/docs/handbook/release-notes/overview.html",
        },
        "vue": {
            "lts": ["3"],
            "eol": ["2"],
            "upgrade_guide": "https://v3-migration.vuejs.org/",
        },
        "angular": {
            "lts": ["17", "18"],
            "eol": ["15", "16"],
            "upgrade_guide": "https://update.angular.io/",
        },
    }

    def check(self, project_dir: Path) -> list[DependencyFinding]:
        """Check framework versions for compatibility.

        Args:
            project_dir: Project directory path

        Returns:
            List of findings
        """
        findings = []

        package_json = project_dir / "package.json"
        if not package_json.exists():
            return findings

        try:
            pkg = json.loads(package_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            for framework, version_info in self.FRAMEWORK_VERSIONS.items():
                if framework in deps:
                    version = deps[framework].lstrip("^~")
                    major_version = version.split(".")[0]

                    if major_version in version_info["eol"]:
                        findings.append(
                            DependencyFinding(
                                severity=DependencySeverity.MEDIUM,
                                category="framework",
                                package=framework,
                                message=f"Framework version {version} may be approaching EOL",
                                current_version=version,
                                recommended_version=f"{version_info['lts'][0]}.x",
                                file="package.json",
                            )
                        )
                    elif major_version not in version_info["lts"]:
                        # Check if it's an older version
                        try:
                            current_major = int(major_version)
                            lts_majors = [int(v) for v in version_info["lts"]]
                            if current_major < min(lts_majors):
                                findings.append(
                                    DependencyFinding(
                                        severity=DependencySeverity.LOW,
                                        category="framework",
                                        package=framework,
                                        message=f"Newer LTS version available ({version_info['lts'][0]}.x)",
                                        current_version=version,
                                        recommended_version=f"{version_info['lts'][0]}.x",
                                        file="package.json",
                                    )
                                )
                        except ValueError:
                            pass

        except json.JSONDecodeError:
            logger.warning("Could not parse package.json")
        except Exception as e:
            logger.warning(f"Framework version check failed: {e}")

        return findings


class DependencyChecker:
    """Main dependency checker that coordinates all strategies."""

    def __init__(
        self,
        project_dir: Path,
        check_npm: bool = True,
        check_docker: bool = True,
        check_frameworks: bool = True,
        blocking_severities: list[DependencySeverity] = None,
    ):
        """Initialize the dependency checker.

        Args:
            project_dir: Project directory path
            check_npm: Whether to check npm dependencies
            check_docker: Whether to check Docker files
            check_frameworks: Whether to check framework versions
            blocking_severities: Severities that block the workflow
        """
        self.project_dir = Path(project_dir)
        self.check_npm = check_npm
        self.check_docker = check_docker
        self.check_frameworks = check_frameworks
        self.blocking_severities = blocking_severities or [
            DependencySeverity.CRITICAL,
            DependencySeverity.HIGH,
        ]

        # Initialize strategies
        self.strategies: list[DependencyStrategy] = []
        if check_npm:
            self.strategies.append(NpmDependencyStrategy())
        if check_docker:
            self.strategies.append(DockerImageStrategy())
        if check_frameworks:
            self.strategies.append(FrameworkVersionStrategy())

    def check(self) -> DependencyCheckResult:
        """Run all dependency checks.

        Returns:
            DependencyCheckResult with all findings
        """
        all_findings: list[DependencyFinding] = []

        # Run all strategies
        for strategy in self.strategies:
            try:
                findings = strategy.check(self.project_dir)
                all_findings.extend(findings)
            except Exception as e:
                logger.warning(f"Strategy {strategy.__class__.__name__} failed: {e}")

        # Count blocking findings
        blocking_findings = sum(1 for f in all_findings if f.severity in self.blocking_severities)

        # Build analysis sections
        npm_analysis = self._build_npm_analysis(all_findings)
        docker_analysis = self._build_docker_analysis(all_findings)
        framework_analysis = self._build_framework_analysis(all_findings)

        # Build recommendations
        recommendations = self._build_recommendations(all_findings)

        # Build auto-fixable section
        auto_fixable = self._build_auto_fixable(all_findings)

        # Determine pass/fail
        passed = blocking_findings == 0

        return DependencyCheckResult(
            passed=passed,
            total_findings=len(all_findings),
            blocking_findings=blocking_findings,
            findings=all_findings,
            npm_analysis=npm_analysis,
            docker_analysis=docker_analysis,
            framework_analysis=framework_analysis,
            recommendations=recommendations,
            auto_fixable=auto_fixable,
        )

    def _build_npm_analysis(self, findings: list[DependencyFinding]) -> dict:
        """Build npm analysis section."""
        npm_findings = [f for f in findings if f.category == "npm"]
        vulnerabilities = [f for f in npm_findings if f.cve]
        outdated = [f for f in npm_findings if not f.cve]

        return {
            "outdated_count": len(outdated),
            "vulnerability_count": len(vulnerabilities),
            "packages": [
                {
                    "name": f.package,
                    "current": f.current_version,
                    "latest": f.recommended_version,
                    "type": "vulnerability" if f.cve else "outdated",
                    "auto_fixable": f.auto_fixable,
                }
                for f in npm_findings[:20]  # Limit
            ],
            "vulnerabilities": [
                {
                    "package": f.package,
                    "severity": f.severity.value,
                    "cve": f.cve,
                    "title": f.message,
                }
                for f in vulnerabilities[:10]
            ],
        }

    def _build_docker_analysis(self, findings: list[DependencyFinding]) -> dict:
        """Build Docker analysis section."""
        docker_findings = [f for f in findings if f.category == "docker"]

        return {
            "findings": [
                {
                    "file": f.file,
                    "line": f.line,
                    "severity": f.severity.value.upper(),
                    "issue": f.message,
                    "current": f.current_version,
                    "recommended": f.recommended_version,
                }
                for f in docker_findings
            ]
        }

    def _build_framework_analysis(self, findings: list[DependencyFinding]) -> dict:
        """Build framework analysis section."""
        framework_findings = [f for f in findings if f.category == "framework"]

        return {
            "findings": [
                {
                    "framework": f.package,
                    "current": f.current_version,
                    "latest_lts": f.recommended_version,
                    "severity": f.severity.value.upper(),
                    "message": f.message,
                }
                for f in framework_findings
            ]
        }

    def _build_recommendations(self, findings: list[DependencyFinding]) -> list[dict]:
        """Build recommendations list."""
        recommendations = []

        # Sort by severity
        sorted_findings = sorted(findings, key=lambda f: list(DependencySeverity).index(f.severity))

        for finding in sorted_findings[:10]:  # Top 10 recommendations
            priority = (
                "CRITICAL"
                if finding.severity == DependencySeverity.CRITICAL
                else "HIGH"
                if finding.severity == DependencySeverity.HIGH
                else "MEDIUM"
                if finding.severity == DependencySeverity.MEDIUM
                else "LOW"
            )

            recommendations.append(
                {
                    "priority": priority,
                    "action": finding.message,
                    "package": finding.package,
                    "command": finding.fix_command,
                }
            )

        return recommendations

    def _build_auto_fixable(self, findings: list[DependencyFinding]) -> dict:
        """Build auto-fixable section."""
        auto_fixable_findings = [f for f in findings if f.auto_fixable]

        patch_updates = [
            f.package
            for f in auto_fixable_findings
            if "patch" in str(f.message).lower() or f.category == "npm"
        ]

        return {
            "patch_updates": patch_updates[:20],
            "command": "npm update" if patch_updates else None,
        }
