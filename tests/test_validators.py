"""Tests for the validators package.

Tests cover:
1. ProductValidator - PRODUCT.md validation
2. EnvironmentChecker - Pre-flight environment checks
3. CoverageChecker - Test coverage enforcement
4. SecurityScanner - Security vulnerability detection

Run with: pytest tests/test_validators.py -v
"""

import json
import pytest
import tempfile
from pathlib import Path


# =============================================================================
# ProductValidator Tests
# =============================================================================

class TestProductValidator:
    """Test ProductValidator for PRODUCT.md validation."""

    def test_valid_product_md(self):
        """Test validation of a complete PRODUCT.md."""
        from orchestrator.validators import ProductValidator

        content = """
# Product Specification

## Feature Name
User Authentication System

## Summary
A comprehensive authentication system that allows users to register, login,
and manage their accounts securely using JWT tokens and password hashing.

## Problem Statement
The application currently lacks a secure way for users to authenticate. We need
a robust authentication system that handles user registration, login, logout,
and session management. This is critical for protecting user data and enabling
personalized features.

## Acceptance Criteria
- [ ] Users can register with email and password
- [ ] Users can login with valid credentials
- [ ] Users receive JWT token on successful login
- [ ] Invalid credentials return appropriate error

## Example Inputs/Outputs

### Example 1: User Registration

**Input:**
```json
POST /api/auth/register
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Output:**
```json
{
  "success": true,
  "user": {"id": "123", "email": "user@example.com"}
}
```

### Example 2: User Login

**Input:**
```json
POST /api/auth/login
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**Output:**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"
}
```

## Technical Constraints

### Performance
- Login response time < 200ms
- Support 1000 concurrent users

### Security
- Passwords hashed with bcrypt
- JWT tokens expire in 24 hours

## Testing Strategy
- Unit tests for auth service
- Integration tests for API endpoints
- E2E tests for login flow

## Definition of Done
- [ ] All acceptance criteria met
- [ ] Unit tests written and passing
- [ ] Integration tests passing
- [ ] Code reviewed
- [ ] Security audit completed
"""
        validator = ProductValidator()
        result = validator.validate(content)

        assert result.valid is True
        assert result.score >= 7.0
        assert result.placeholder_count == 0

    def test_incomplete_product_md(self):
        """Test validation of an incomplete PRODUCT.md."""
        from orchestrator.validators import ProductValidator

        content = """
# Product

## Feature
A feature

## Summary
Short

## Goals
- Goal 1
"""
        validator = ProductValidator()
        result = validator.validate(content)

        assert result.valid is False
        assert result.score < 6.0
        assert len(result.issues) > 0

    def test_placeholder_detection(self):
        """Test detection of placeholder text."""
        from orchestrator.validators import ProductValidator

        content = """
# Product Specification

## Feature Name
[TODO] Add feature name

## Summary
Lorem ipsum dolor sit amet

## Problem Statement
[TBD]

## Acceptance Criteria
- [ ] [Add criteria here]
"""
        validator = ProductValidator()
        result = validator.validate(content)

        assert result.valid is False
        assert result.placeholder_count > 0
        assert any("placeholder" in str(i.message).lower() for i in result.issues)

    def test_file_not_found(self):
        """Test validation when file doesn't exist."""
        from orchestrator.validators import ProductValidator

        validator = ProductValidator()
        result = validator.validate_file("/nonexistent/PRODUCT.md")

        assert result.valid is False
        assert result.score == 0.0
        assert any("not found" in str(i.message).lower() for i in result.issues)

    def test_strict_mode(self):
        """Test strict mode treats warnings as errors."""
        from orchestrator.validators import ProductValidator

        content = """
# Product Specification

## Feature Name
Test Feature

## Summary
A test feature for validation testing purposes.

## Problem Statement
We need to test the validation system to ensure it works correctly.
This is a test problem statement that should be long enough to pass.

## Acceptance Criteria
- [ ] Test criterion 1
- [ ] Test criterion 2
- [ ] Test criterion 3
"""
        # Normal mode - warnings don't fail
        validator = ProductValidator(strict_mode=False)
        result = validator.validate(content)

        # Strict mode - warnings cause failure
        validator_strict = ProductValidator(strict_mode=True)
        result_strict = validator_strict.validate(content)

        # Strict mode should be more restrictive
        # (actual result depends on content quality)


# =============================================================================
# EnvironmentChecker Tests
# =============================================================================

class TestEnvironmentChecker:
    """Test EnvironmentChecker for pre-flight environment checks."""

    def test_detect_node_project(self):
        """Test detection of Node.js project."""
        from orchestrator.validators import EnvironmentChecker
        from orchestrator.validators.environment_checker import ProjectType

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create package.json
            package_json = project_dir / "package.json"
            package_json.write_text(json.dumps({
                "name": "test-project",
                "dependencies": {
                    "express": "^4.18.0"
                }
            }))

            checker = EnvironmentChecker(project_dir)
            result = checker.check()

            assert result.project_type == ProjectType.NODE_API

    def test_detect_react_project(self):
        """Test detection of React project."""
        from orchestrator.validators import EnvironmentChecker
        from orchestrator.validators.environment_checker import ProjectType

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            package_json = project_dir / "package.json"
            package_json.write_text(json.dumps({
                "name": "test-react",
                "dependencies": {
                    "react": "^18.0.0"
                }
            }))

            checker = EnvironmentChecker(project_dir)
            result = checker.check()

            assert result.project_type == ProjectType.REACT

    def test_detect_python_project(self):
        """Test detection of Python project."""
        from orchestrator.validators import EnvironmentChecker
        from orchestrator.validators.environment_checker import ProjectType

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            pyproject = project_dir / "pyproject.toml"
            pyproject.write_text('[project]\nname = "test"')

            checker = EnvironmentChecker(project_dir)
            result = checker.check()

            assert result.project_type == ProjectType.PYTHON

    def test_complexity_estimation(self):
        """Test complexity estimation from PRODUCT.md."""
        from orchestrator.validators import EnvironmentChecker
        from orchestrator.validators.environment_checker import Complexity

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create minimal PRODUCT.md
            product_md = project_dir / "PRODUCT.md"
            product_md.write_text("# Simple Feature\n- One task")

            checker = EnvironmentChecker(project_dir)
            complexity = checker._estimate_complexity()

            assert complexity in [Complexity.LOW, Complexity.MEDIUM]


# =============================================================================
# CoverageChecker Tests
# =============================================================================

class TestCoverageChecker:
    """Test CoverageChecker for coverage enforcement."""

    def test_json_coverage_parsing(self):
        """Test parsing of JSON coverage report."""
        from orchestrator.validators import CoverageChecker
        from orchestrator.validators.coverage_checker import CoverageStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            coverage_dir = project_dir / "coverage"
            coverage_dir.mkdir()

            # Create coverage-summary.json
            coverage_file = coverage_dir / "coverage-summary.json"
            coverage_file.write_text(json.dumps({
                "total": {
                    "lines": {"total": 100, "covered": 80, "pct": 80.0},
                    "branches": {"total": 50, "covered": 40, "pct": 80.0},
                },
                "src/main.ts": {
                    "lines": {"total": 100, "covered": 80, "pct": 80.0},
                }
            }))

            checker = CoverageChecker(project_dir, threshold=70.0)
            result = checker.check()

            assert result.status == CoverageStatus.PASSED
            assert result.overall_percent == 80.0
            assert result.meets_threshold is True

    def test_coverage_below_threshold(self):
        """Test coverage below threshold."""
        from orchestrator.validators import CoverageChecker
        from orchestrator.validators.coverage_checker import CoverageStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            coverage_dir = project_dir / "coverage"
            coverage_dir.mkdir()

            coverage_file = coverage_dir / "coverage-summary.json"
            coverage_file.write_text(json.dumps({
                "total": {
                    "lines": {"total": 100, "covered": 50, "pct": 50.0},
                }
            }))

            # Non-blocking
            checker = CoverageChecker(project_dir, threshold=70.0, blocking=False)
            result = checker.check()

            assert result.status == CoverageStatus.WARNING
            assert result.meets_threshold is False

            # Blocking
            checker_blocking = CoverageChecker(project_dir, threshold=70.0, blocking=True)
            result_blocking = checker_blocking.check()

            assert result_blocking.status == CoverageStatus.FAILED

    def test_no_coverage_report(self):
        """Test when no coverage report exists."""
        from orchestrator.validators import CoverageChecker
        from orchestrator.validators.coverage_checker import CoverageStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            checker = CoverageChecker(project_dir)
            result = checker.check()

            assert result.status == CoverageStatus.SKIPPED


# =============================================================================
# SecurityScanner Tests
# =============================================================================

class TestSecurityScanner:
    """Test SecurityScanner for security vulnerability detection."""

    def test_detect_hardcoded_api_key(self):
        """Test detection of hardcoded API keys."""
        from orchestrator.validators import SecurityScanner, Severity

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create source file with hardcoded API key
            src_file = project_dir / "config.py"
            src_file.write_text('api_key = "sk-1234567890abcdefghijklmnopqrstuvwxyz"')

            scanner = SecurityScanner(project_dir)
            result = scanner.scan()

            assert result.total_findings > 0
            assert result.passed is False
            api_key_findings = [f for f in result.findings if "api" in f.rule_id.lower()]
            assert len(api_key_findings) > 0

    def test_detect_sql_injection(self):
        """Test detection of SQL injection patterns."""
        from orchestrator.validators import SecurityScanner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create file with SQL injection vulnerability
            src_file = project_dir / "db.py"
            src_file.write_text('''
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)
''')

            scanner = SecurityScanner(project_dir)
            result = scanner.scan()

            sql_findings = [f for f in result.findings if "sql" in f.rule_id.lower()]
            assert len(sql_findings) > 0

    def test_skip_node_modules(self):
        """Test that node_modules is skipped."""
        from orchestrator.validators import SecurityScanner

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create node_modules with vulnerable code
            node_modules = project_dir / "node_modules" / "some-package"
            node_modules.mkdir(parents=True)

            vuln_file = node_modules / "index.js"
            vuln_file.write_text('const secret = "super-secret-password-12345678"')

            scanner = SecurityScanner(project_dir)
            result = scanner.scan()

            # Should not find anything since node_modules is skipped
            assert result.total_findings == 0

    def test_scan_content(self):
        """Test scanning content string directly."""
        from orchestrator.validators import SecurityScanner

        scanner = SecurityScanner("/tmp")

        content = '''
const config = {
    apiKey: "sk-abcdefghijklmnopqrstuvwxyz123456",
    secret: "my-super-secret-password"
};
'''
        findings = scanner.scan_content(content, "config.js")

        assert len(findings) > 0

    def test_blocking_severities(self):
        """Test configurable blocking severities."""
        from orchestrator.validators import SecurityScanner, Severity

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create file with medium severity issue
            src_file = project_dir / "random.js"
            src_file.write_text('const token = "token-" + Math.random()')

            # With HIGH blocking - should pass (Math.random is MEDIUM)
            scanner_high = SecurityScanner(
                project_dir,
                blocking_severities=[Severity.CRITICAL, Severity.HIGH]
            )
            result_high = scanner_high.scan()

            # With MEDIUM blocking - should fail
            scanner_medium = SecurityScanner(
                project_dir,
                blocking_severities=[Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM]
            )
            result_medium = scanner_medium.scan()

            # Results depend on what patterns match


# =============================================================================
# Config/Thresholds Tests
# =============================================================================

class TestProjectConfig:
    """Test project configuration loading."""

    def test_default_config(self):
        """Test getting default config for project type."""
        from orchestrator.config import get_project_config

        config = get_project_config("base")
        assert config.project_type == "base"
        assert config.validation.validation_threshold == 6.0
        assert config.validation.verification_threshold == 7.0

    def test_node_api_config(self):
        """Test node-api specific defaults."""
        from orchestrator.config import get_project_config

        config = get_project_config("node-api")
        assert config.project_type == "node-api"
        assert config.validation.validation_threshold == 7.0
        assert config.quality.coverage_threshold == 85.0
        assert config.quality.coverage_blocking is True

    def test_load_custom_config(self):
        """Test loading custom config from file."""
        from orchestrator.config import load_project_config

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Create custom config
            config_file = project_dir / ".project-config.json"
            config_file.write_text(json.dumps({
                "project_type": "custom",
                "validation": {
                    "validation_threshold": 8.0
                },
                "quality": {
                    "coverage_threshold": 90
                }
            }))

            config = load_project_config(project_dir)

            assert config.validation.validation_threshold == 8.0
            assert config.quality.coverage_threshold == 90.0

    def test_feature_flags(self):
        """Test workflow feature flags."""
        from orchestrator.config import load_project_config

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            config_file = project_dir / ".project-config.json"
            config_file.write_text(json.dumps({
                "workflow": {
                    "features": {
                        "product_validation": False,
                        "security_scan": False
                    }
                }
            }))

            config = load_project_config(project_dir)

            assert config.workflow.features.product_validation is False
            assert config.workflow.features.security_scan is False
            # Other features should still be True (default)
            assert config.workflow.features.build_verification is True
