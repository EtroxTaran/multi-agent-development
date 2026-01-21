"""Configurable thresholds for workflow validation and quality gates.

Provides project-type specific defaults and loading from .project-config.json.
"""

import copy
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..validators.security_scanner import Severity

logger = logging.getLogger(__name__)


@dataclass
class ValidationConfig:
    """Configuration for validation thresholds."""
    validation_threshold: float = 6.0  # Phase 2 minimum score
    verification_threshold: float = 7.0  # Phase 4 minimum score
    max_phase_retries: int = 3


@dataclass
class QualityConfig:
    """Configuration for code quality gates."""
    coverage_threshold: float = 70.0
    coverage_blocking: bool = False
    build_required: bool = True
    lint_required: bool = False


@dataclass
class SecurityConfig:
    """Configuration for security scanning."""
    enabled: bool = True
    blocking_severities: list[Severity] = field(
        default_factory=lambda: [Severity.CRITICAL, Severity.HIGH]
    )


@dataclass
class WorkflowFeatures:
    """Feature flags for workflow nodes."""
    product_validation: bool = True
    environment_check: bool = True
    build_verification: bool = True
    coverage_check: bool = True
    security_scan: bool = True
    approval_gates: bool = False  # Human approval gates


@dataclass
class WorkflowConfig:
    """Configuration for workflow behavior."""
    features: WorkflowFeatures = field(default_factory=WorkflowFeatures)
    approval_phases: list[int] = field(default_factory=list)  # Phases requiring human approval


@dataclass
class ProjectConfig:
    """Complete project configuration."""
    project_type: str = "base"
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "project_type": self.project_type,
            "validation": {
                "validation_threshold": self.validation.validation_threshold,
                "verification_threshold": self.validation.verification_threshold,
                "max_phase_retries": self.validation.max_phase_retries,
            },
            "quality": {
                "coverage_threshold": self.quality.coverage_threshold,
                "coverage_blocking": self.quality.coverage_blocking,
                "build_required": self.quality.build_required,
                "lint_required": self.quality.lint_required,
            },
            "security": {
                "enabled": self.security.enabled,
                "blocking_severities": [s.value for s in self.security.blocking_severities],
            },
            "workflow": {
                "features": {
                    "product_validation": self.workflow.features.product_validation,
                    "environment_check": self.workflow.features.environment_check,
                    "build_verification": self.workflow.features.build_verification,
                    "coverage_check": self.workflow.features.coverage_check,
                    "security_scan": self.workflow.features.security_scan,
                    "approval_gates": self.workflow.features.approval_gates,
                },
                "approval_phases": self.workflow.approval_phases,
            },
        }


# Project-type specific defaults
DEFAULT_CONFIGS: dict[str, ProjectConfig] = {
    "base": ProjectConfig(
        project_type="base",
        validation=ValidationConfig(
            validation_threshold=6.0,
            verification_threshold=7.0,
        ),
        quality=QualityConfig(
            coverage_threshold=70.0,
            coverage_blocking=False,
        ),
    ),
    "react-tanstack": ProjectConfig(
        project_type="react-tanstack",
        validation=ValidationConfig(
            validation_threshold=6.5,
            verification_threshold=7.5,
        ),
        quality=QualityConfig(
            coverage_threshold=80.0,
            coverage_blocking=False,
        ),
    ),
    "node-api": ProjectConfig(
        project_type="node-api",
        validation=ValidationConfig(
            validation_threshold=7.0,
            verification_threshold=8.0,
        ),
        quality=QualityConfig(
            coverage_threshold=85.0,
            coverage_blocking=True,  # APIs need high coverage
        ),
    ),
    "java-spring": ProjectConfig(
        project_type="java-spring",
        validation=ValidationConfig(
            validation_threshold=7.0,
            verification_threshold=8.0,
        ),
        quality=QualityConfig(
            coverage_threshold=80.0,
            coverage_blocking=True,
        ),
    ),
    "nx-fullstack": ProjectConfig(
        project_type="nx-fullstack",
        validation=ValidationConfig(
            validation_threshold=6.5,
            verification_threshold=7.5,
        ),
        quality=QualityConfig(
            coverage_threshold=75.0,
            coverage_blocking=False,
        ),
    ),
    "python": ProjectConfig(
        project_type="python",
        validation=ValidationConfig(
            validation_threshold=6.5,
            verification_threshold=7.5,
        ),
        quality=QualityConfig(
            coverage_threshold=80.0,
            coverage_blocking=False,
        ),
    ),
}


def get_project_config(project_type: str) -> ProjectConfig:
    """Get configuration for a project type.

    Args:
        project_type: Type of project (e.g., "react-tanstack", "node-api")

    Returns:
        ProjectConfig with type-specific defaults (a fresh copy)
    """
    if project_type in DEFAULT_CONFIGS:
        # Return a deep copy to prevent mutation of shared defaults
        return copy.deepcopy(DEFAULT_CONFIGS[project_type])

    # Return base config for unknown types
    logger.warning(f"Unknown project type '{project_type}', using base defaults")
    config = copy.deepcopy(DEFAULT_CONFIGS["base"])
    config.project_type = project_type
    return config


def load_project_config(project_dir: str | Path) -> ProjectConfig:
    """Load project configuration from .project-config.json.

    Falls back to detecting project type from files if no config exists.

    Args:
        project_dir: Path to the project directory

    Returns:
        ProjectConfig with merged settings
    """
    project_dir = Path(project_dir)
    config_file = project_dir / ".project-config.json"

    # Start with base config
    config = ProjectConfig()

    # Try to detect project type from template.json or package.json
    template_file = project_dir / "template.json"
    package_file = project_dir / "package.json"

    detected_type = "base"

    if template_file.exists():
        try:
            template = json.loads(template_file.read_text())
            detected_type = template.get("name", "base")
        except Exception:
            pass
    elif package_file.exists():
        try:
            pkg = json.loads(package_file.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            if "react" in deps:
                if "tanstack" in str(deps).lower():
                    detected_type = "react-tanstack"
                else:
                    detected_type = "react-tanstack"  # Default React to tanstack
            elif "express" in deps or "fastify" in deps or "hono" in deps:
                detected_type = "node-api"
            else:
                detected_type = "base"
        except Exception:
            pass

    # Get defaults for detected type
    config = get_project_config(detected_type)

    # Load custom config if exists
    if config_file.exists():
        try:
            custom = json.loads(config_file.read_text())
            config = _merge_config(config, custom)
            logger.info(f"Loaded custom config from {config_file}")
        except Exception as e:
            logger.warning(f"Error loading config from {config_file}: {e}")

    return config


def _merge_config(base: ProjectConfig, custom: dict) -> ProjectConfig:
    """Merge custom config into base config.

    Args:
        base: Base ProjectConfig
        custom: Custom config dictionary

    Returns:
        Merged ProjectConfig
    """
    # Update project type
    if "project_type" in custom:
        base.project_type = custom["project_type"]

    # Update validation config
    if "validation" in custom:
        v = custom["validation"]
        if "validation_threshold" in v:
            base.validation.validation_threshold = float(v["validation_threshold"])
        if "verification_threshold" in v:
            base.validation.verification_threshold = float(v["verification_threshold"])
        if "max_phase_retries" in v:
            base.validation.max_phase_retries = int(v["max_phase_retries"])

    # Update quality config
    if "quality" in custom:
        q = custom["quality"]
        if "coverage_threshold" in q:
            base.quality.coverage_threshold = float(q["coverage_threshold"])
        if "coverage_blocking" in q:
            base.quality.coverage_blocking = bool(q["coverage_blocking"])
        if "build_required" in q:
            base.quality.build_required = bool(q["build_required"])
        if "lint_required" in q:
            base.quality.lint_required = bool(q["lint_required"])

    # Update security config
    if "security" in custom:
        s = custom["security"]
        if "enabled" in s:
            base.security.enabled = bool(s["enabled"])
        if "blocking_severities" in s:
            base.security.blocking_severities = [
                Severity(sev) for sev in s["blocking_severities"]
                if sev in [e.value for e in Severity]
            ]

    # Update workflow config
    if "workflow" in custom:
        w = custom["workflow"]
        if "features" in w:
            f = w["features"]
            if "product_validation" in f:
                base.workflow.features.product_validation = bool(f["product_validation"])
            if "environment_check" in f:
                base.workflow.features.environment_check = bool(f["environment_check"])
            if "build_verification" in f:
                base.workflow.features.build_verification = bool(f["build_verification"])
            if "coverage_check" in f:
                base.workflow.features.coverage_check = bool(f["coverage_check"])
            if "security_scan" in f:
                base.workflow.features.security_scan = bool(f["security_scan"])
            if "approval_gates" in f:
                base.workflow.features.approval_gates = bool(f["approval_gates"])
        if "approval_phases" in w:
            base.workflow.approval_phases = list(w["approval_phases"])

    return base


def save_project_config(project_dir: str | Path, config: ProjectConfig) -> None:
    """Save project configuration to .project-config.json.

    Args:
        project_dir: Path to the project directory
        config: ProjectConfig to save
    """
    project_dir = Path(project_dir)
    config_file = project_dir / ".project-config.json"

    config_dict = config.to_dict()

    config_file.write_text(json.dumps(config_dict, indent=2))
    logger.info(f"Saved config to {config_file}")
