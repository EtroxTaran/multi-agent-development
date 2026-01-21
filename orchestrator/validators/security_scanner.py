"""Security scanner for code vulnerability detection.

Performs pattern-based static analysis to detect common security
vulnerabilities like hardcoded secrets, SQL injection, XSS, etc.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    """Severity levels for security findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SecurityFinding:
    """A single security finding."""
    rule_id: str
    severity: Severity
    message: str
    file_path: str
    line_number: int
    line_content: str
    suggestion: Optional[str] = None
    cwe_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "line_content": self.line_content[:200],  # Truncate long lines
            "suggestion": self.suggestion,
            "cwe_id": self.cwe_id,
        }


@dataclass
class SecurityScanResult:
    """Result of security scan."""
    passed: bool
    total_findings: int
    findings_by_severity: dict[Severity, int] = field(default_factory=dict)
    findings: list[SecurityFinding] = field(default_factory=list)
    files_scanned: int = 0
    blocking_findings: int = 0

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_findings": self.total_findings,
            "findings_by_severity": {k.value: v for k, v in self.findings_by_severity.items()},
            "findings": [f.to_dict() for f in self.findings],
            "files_scanned": self.files_scanned,
            "blocking_findings": self.blocking_findings,
        }


# Security rules with patterns
SECURITY_RULES = [
    # Hardcoded secrets
    {
        "id": "hardcoded-api-key",
        "severity": Severity.HIGH,
        "message": "Possible hardcoded API key detected",
        "pattern": r"""(?:api[_-]?key|apikey)\s*[=:]\s*['"][a-zA-Z0-9_\-]{20,}['"]""",
        "suggestion": "Use environment variables for API keys",
        "cwe": "CWE-798",
        "languages": ["all"],
    },
    {
        "id": "hardcoded-secret",
        "severity": Severity.HIGH,
        "message": "Possible hardcoded secret detected",
        "pattern": r"""(?:secret|password|passwd|pwd)\s*[=:]\s*['"][^'"]{8,}['"]""",
        "suggestion": "Use environment variables or a secrets manager",
        "cwe": "CWE-798",
        "languages": ["all"],
    },
    {
        "id": "aws-credentials",
        "severity": Severity.CRITICAL,
        "message": "AWS credentials detected",
        "pattern": r"""(?:AWS_SECRET_ACCESS_KEY|aws_secret_access_key)\s*[=:]\s*['"][A-Za-z0-9/+=]{40}['"]""",
        "suggestion": "Use IAM roles or AWS Secrets Manager instead",
        "cwe": "CWE-798",
        "languages": ["all"],
    },
    {
        "id": "private-key",
        "severity": Severity.CRITICAL,
        "message": "Private key detected in source code",
        "pattern": r"""-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----""",
        "suggestion": "Store private keys in a secure secrets manager",
        "cwe": "CWE-321",
        "languages": ["all"],
    },
    # SQL Injection
    {
        "id": "sql-injection-fstring",
        "severity": Severity.CRITICAL,
        "message": "Possible SQL injection via f-string interpolation",
        "pattern": r"""f['"]{1,3}(?:[^'"]*(?:SELECT|INSERT|UPDATE|DELETE|DROP)[^'"]*\{[^}]+\}[^'"]*)['"]{1,3}""",
        "suggestion": "Use parameterized queries instead of string interpolation",
        "cwe": "CWE-89",
        "languages": ["python"],
    },
    {
        "id": "sql-injection-concat",
        "severity": Severity.CRITICAL,
        "message": "Possible SQL injection via string concatenation",
        "pattern": r"""(?:SELECT|INSERT|UPDATE|DELETE|DROP)\s+[^;]*\s*\+\s*(?:req\.|request\.|params\.|body\.)""",
        "suggestion": "Use parameterized queries instead of string concatenation",
        "cwe": "CWE-89",
        "languages": ["javascript", "typescript"],
    },
    {
        "id": "sql-injection-template",
        "severity": Severity.CRITICAL,
        "message": "Possible SQL injection via template literal",
        "pattern": r"""`(?:[^`]*(?:SELECT|INSERT|UPDATE|DELETE|DROP)[^`]*\$\{[^}]+\}[^`]*)`""",
        "suggestion": "Use parameterized queries instead of template literals",
        "cwe": "CWE-89",
        "languages": ["javascript", "typescript"],
    },
    # Command Injection
    {
        "id": "command-injection-exec",
        "severity": Severity.CRITICAL,
        "message": "Possible command injection via exec/system call",
        "pattern": r"""(?:exec|system|popen|subprocess\.(?:run|call|Popen))\s*\([^)]*(?:req\.|request\.|params\.|user|input)""",
        "suggestion": "Sanitize user input or use subprocess with shell=False",
        "cwe": "CWE-78",
        "languages": ["python"],
    },
    {
        "id": "command-injection-child-process",
        "severity": Severity.HIGH,
        "message": "Possible command injection in child_process",
        "pattern": r"""(?:child_process\.exec|execSync)\s*\([^)]*(?:\$\{|req\.|request\.)""",
        "suggestion": "Use execFile or spawn with explicit arguments array",
        "cwe": "CWE-78",
        "languages": ["javascript", "typescript"],
    },
    # XSS
    {
        "id": "xss-innerhtml",
        "severity": Severity.HIGH,
        "message": "Possible XSS via innerHTML assignment",
        "pattern": r"""\.innerHTML\s*=\s*(?!['"`]<[^>]+>['"`])""",
        "suggestion": "Use textContent or sanitize HTML before setting innerHTML",
        "cwe": "CWE-79",
        "languages": ["javascript", "typescript"],
    },
    {
        "id": "xss-dangerously-set",
        "severity": Severity.MEDIUM,
        "message": "React dangerouslySetInnerHTML usage detected",
        "pattern": r"""dangerouslySetInnerHTML\s*=\s*\{""",
        "suggestion": "Ensure content is properly sanitized before use",
        "cwe": "CWE-79",
        "languages": ["javascript", "typescript", "jsx", "tsx"],
    },
    # Eval and exec
    {
        "id": "dangerous-eval",
        "severity": Severity.HIGH,
        "message": "Use of eval() with potentially unsafe input",
        "pattern": r"""eval\s*\([^)]*(?:req\.|request\.|params\.|user|input|\$\{)""",
        "suggestion": "Avoid eval() with user input; use JSON.parse() for JSON",
        "cwe": "CWE-95",
        "languages": ["all"],
    },
    {
        "id": "python-exec",
        "severity": Severity.HIGH,
        "message": "Use of exec() detected",
        "pattern": r"""exec\s*\([^)]+\)""",
        "suggestion": "Avoid exec() with user-controlled input",
        "cwe": "CWE-95",
        "languages": ["python"],
    },
    # Insecure randomness
    {
        "id": "insecure-random-js",
        "severity": Severity.MEDIUM,
        "message": "Math.random() used for potentially security-sensitive operation",
        "pattern": r"""(?:token|secret|key|password|auth|session)\s*[=:][^;]*Math\.random\(\)""",
        "suggestion": "Use crypto.randomBytes() or crypto.randomUUID() for security-sensitive randomness",
        "cwe": "CWE-330",
        "languages": ["javascript", "typescript"],
    },
    {
        "id": "insecure-random-python",
        "severity": Severity.MEDIUM,
        "message": "random module used for potentially security-sensitive operation",
        "pattern": r"""(?:token|secret|key|password|auth|session)\s*=\s*[^#\n]*random\.""",
        "suggestion": "Use secrets module for security-sensitive randomness",
        "cwe": "CWE-330",
        "languages": ["python"],
    },
    # Path traversal
    {
        "id": "path-traversal",
        "severity": Severity.HIGH,
        "message": "Possible path traversal vulnerability",
        "pattern": r"""(?:path\.join|fs\.read|open)\s*\([^)]*(?:req\.|request\.|params\.)""",
        "suggestion": "Validate and sanitize file paths; use path.resolve() and check prefix",
        "cwe": "CWE-22",
        "languages": ["all"],
    },
    # Weak crypto
    {
        "id": "weak-hash-md5",
        "severity": Severity.MEDIUM,
        "message": "Use of weak MD5 hash algorithm",
        "pattern": r"""(?:md5|MD5)\s*\(""",
        "suggestion": "Use SHA-256 or stronger hash algorithms",
        "cwe": "CWE-328",
        "languages": ["all"],
    },
    {
        "id": "weak-hash-sha1",
        "severity": Severity.LOW,
        "message": "Use of weak SHA1 hash algorithm",
        "pattern": r"""(?:sha1|SHA1|createHash\s*\(\s*['"]sha1['"]\))\s*\(""",
        "suggestion": "Use SHA-256 or stronger hash algorithms for security purposes",
        "cwe": "CWE-328",
        "languages": ["all"],
    },
    # Hardcoded JWT secrets
    {
        "id": "hardcoded-jwt-secret",
        "severity": Severity.HIGH,
        "message": "Possible hardcoded JWT secret",
        "pattern": r"""(?:jwt\.sign|jwt\.verify|jsonwebtoken\.sign)\s*\([^)]*['"][a-zA-Z0-9_\-]{16,}['"]""",
        "suggestion": "Store JWT secrets in environment variables",
        "cwe": "CWE-798",
        "languages": ["javascript", "typescript"],
    },
    # CORS wildcard
    {
        "id": "cors-wildcard",
        "severity": Severity.MEDIUM,
        "message": "CORS configured with wildcard origin",
        "pattern": r"""(?:cors|Access-Control-Allow-Origin)[^;]*['"]\*['"]""",
        "suggestion": "Specify explicit allowed origins instead of wildcard",
        "cwe": "CWE-942",
        "languages": ["all"],
    },
    # Debug mode
    {
        "id": "debug-enabled",
        "severity": Severity.MEDIUM,
        "message": "Debug mode appears to be enabled",
        "pattern": r"""(?:DEBUG|debug)\s*[=:]\s*(?:True|true|1|['"]true['"])""",
        "suggestion": "Ensure debug mode is disabled in production",
        "cwe": "CWE-489",
        "languages": ["all"],
    },
]

# File extensions to scan
SCANNABLE_EXTENSIONS = {
    "all": {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".php", ".cs"},
    "python": {".py"},
    "javascript": {".js", ".jsx"},
    "typescript": {".ts", ".tsx"},
    "jsx": {".jsx"},
    "tsx": {".tsx"},
    "java": {".java"},
    "go": {".go"},
    "rust": {".rs"},
}

# Directories to skip
SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    "coverage",
    ".mypy_cache",
    ".tox",
    "vendor",
}


class SecurityScanner:
    """Scans source code for security vulnerabilities."""

    def __init__(
        self,
        project_dir: str | Path,
        blocking_severities: Optional[list[Severity]] = None,
    ):
        """Initialize the security scanner.

        Args:
            project_dir: Path to the project directory
            blocking_severities: Severities that block workflow (default: CRITICAL, HIGH)
        """
        self.project_dir = Path(project_dir)
        self.blocking_severities = blocking_severities or [Severity.CRITICAL, Severity.HIGH]

    def scan(self) -> SecurityScanResult:
        """Scan the project for security vulnerabilities.

        Returns:
            SecurityScanResult with all findings
        """
        findings: list[SecurityFinding] = []
        files_scanned = 0

        # Get all source files
        source_files = self._get_source_files()

        for file_path in source_files:
            try:
                file_findings = self._scan_file(file_path)
                findings.extend(file_findings)
                files_scanned += 1
            except Exception as e:
                logger.warning(f"Error scanning {file_path}: {e}")

        # Count findings by severity
        findings_by_severity: dict[Severity, int] = {}
        blocking_count = 0

        for finding in findings:
            findings_by_severity[finding.severity] = findings_by_severity.get(finding.severity, 0) + 1
            if finding.severity in self.blocking_severities:
                blocking_count += 1

        # Determine if scan passed
        passed = blocking_count == 0

        return SecurityScanResult(
            passed=passed,
            total_findings=len(findings),
            findings_by_severity=findings_by_severity,
            findings=findings,
            files_scanned=files_scanned,
            blocking_findings=blocking_count,
        )

    def _get_source_files(self) -> list[Path]:
        """Get all source files to scan."""
        all_extensions = SCANNABLE_EXTENSIONS["all"]
        files = []

        for file_path in self.project_dir.rglob("*"):
            # Skip directories
            if file_path.is_dir():
                continue

            # Skip non-source files
            if file_path.suffix not in all_extensions:
                continue

            # Skip excluded directories
            parts = file_path.relative_to(self.project_dir).parts
            if any(part in SKIP_DIRS for part in parts):
                continue

            files.append(file_path)

        return files

    def _scan_file(self, file_path: Path) -> list[SecurityFinding]:
        """Scan a single file for security issues.

        Args:
            file_path: Path to the file

        Returns:
            List of findings in the file
        """
        findings: list[SecurityFinding] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
        except Exception:
            return findings

        # Determine applicable languages based on extension
        ext = file_path.suffix
        applicable_languages = {"all"}

        for lang, extensions in SCANNABLE_EXTENSIONS.items():
            if lang != "all" and ext in extensions:
                applicable_languages.add(lang)

        # Apply each rule
        for rule in SECURITY_RULES:
            rule_languages = set(rule.get("languages", ["all"]))

            # Check if rule applies to this file type
            if not (rule_languages & applicable_languages):
                continue

            pattern = rule["pattern"]

            try:
                regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)

                for i, line in enumerate(lines, start=1):
                    # Skip comment lines (basic check)
                    stripped = line.strip()
                    if stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("*"):
                        continue

                    if regex.search(line):
                        # Calculate relative path for cleaner output
                        try:
                            rel_path = str(file_path.relative_to(self.project_dir))
                        except ValueError:
                            rel_path = str(file_path)

                        findings.append(SecurityFinding(
                            rule_id=rule["id"],
                            severity=rule["severity"],
                            message=rule["message"],
                            file_path=rel_path,
                            line_number=i,
                            line_content=line.strip(),
                            suggestion=rule.get("suggestion"),
                            cwe_id=rule.get("cwe"),
                        ))

            except re.error as e:
                logger.warning(f"Invalid regex for rule {rule['id']}: {e}")

        return findings

    def scan_content(self, content: str, filename: str = "unknown") -> list[SecurityFinding]:
        """Scan a string content for security issues.

        Useful for scanning generated or in-memory code.

        Args:
            content: Source code content
            filename: Filename for reporting

        Returns:
            List of findings
        """
        findings: list[SecurityFinding] = []
        lines = content.splitlines()

        for rule in SECURITY_RULES:
            pattern = rule["pattern"]

            try:
                regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)

                for i, line in enumerate(lines, start=1):
                    stripped = line.strip()
                    if stripped.startswith("//") or stripped.startswith("#"):
                        continue

                    if regex.search(line):
                        findings.append(SecurityFinding(
                            rule_id=rule["id"],
                            severity=rule["severity"],
                            message=rule["message"],
                            file_path=filename,
                            line_number=i,
                            line_content=line.strip(),
                            suggestion=rule.get("suggestion"),
                            cwe_id=rule.get("cwe"),
                        ))

            except re.error:
                pass

        return findings


def scan_security(
    project_dir: str | Path,
    blocking_severities: Optional[list[Severity]] = None,
) -> SecurityScanResult:
    """Convenience function to scan for security issues.

    Args:
        project_dir: Path to the project directory
        blocking_severities: Severities that block workflow

    Returns:
        SecurityScanResult
    """
    scanner = SecurityScanner(project_dir, blocking_severities)
    return scanner.scan()
