"""Quality gate node.

Runs automated code quality checks:
- TypeScript strict mode validation
- ESLint analysis
- Naming convention checks
- Code structure analysis

This node runs after build_verification and before cursor_review/gemini_review.
"""

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from ...config import load_project_config
from ..state import WorkflowState, create_error_context

logger = logging.getLogger(__name__)


# Severity weights for scoring
SEVERITY_WEIGHTS = {
    "CRITICAL": 3.0,
    "HIGH": 1.5,
    "MEDIUM": 0.5,
    "LOW": 0.1,
    "INFO": 0.0,
}

# TypeScript error code to severity mapping
TS_ERROR_SEVERITY = {
    "TS2304": "CRITICAL",  # Cannot find name
    "TS2307": "CRITICAL",  # Cannot find module
    "TS2322": "HIGH",  # Type mismatch
    "TS2345": "HIGH",  # Argument type
    "TS2339": "HIGH",  # Property does not exist
    "TS7006": "MEDIUM",  # Implicit any
    "TS6133": "LOW",  # Declared but never used
}


def _run_typescript_check(project_dir: Path) -> dict:
    """Run TypeScript compiler in noEmit mode.

    Args:
        project_dir: Project directory path

    Returns:
        Dict with typescript check results
    """
    result = {
        "passed": True,
        "error_count": 0,
        "errors": [],
    }

    # Check if tsconfig.json exists
    tsconfig = project_dir / "tsconfig.json"
    if not tsconfig.exists():
        logger.info("No tsconfig.json found, skipping TypeScript check")
        return result

    try:
        # Run tsc --noEmit
        proc = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if proc.returncode == 0:
            return result

        # Parse TypeScript errors
        error_pattern = re.compile(
            r"^(.+)\((\d+),(\d+)\):\s*error\s+(TS\d+):\s*(.+)$", re.MULTILINE
        )

        for match in error_pattern.finditer(proc.stdout + proc.stderr):
            file_path, line, column, code, message = match.groups()
            severity = TS_ERROR_SEVERITY.get(code, "MEDIUM")

            result["errors"].append(
                {
                    "code": code,
                    "file": str(file_path),
                    "line": int(line),
                    "column": int(column),
                    "message": message.strip(),
                    "severity": severity,
                }
            )

        result["error_count"] = len(result["errors"])
        result["passed"] = result["error_count"] == 0

    except subprocess.TimeoutExpired:
        logger.warning("TypeScript check timed out")
        result["errors"].append(
            {
                "code": "TIMEOUT",
                "message": "TypeScript compilation timed out after 120s",
                "severity": "INFO",
            }
        )
    except FileNotFoundError:
        logger.warning("npx/tsc not found, skipping TypeScript check")
    except Exception as e:
        logger.warning(f"TypeScript check failed: {e}")

    return result


def _run_eslint_check(project_dir: Path) -> dict:
    """Run ESLint with JSON output.

    Args:
        project_dir: Project directory path

    Returns:
        Dict with ESLint check results
    """
    result = {
        "passed": True,
        "error_count": 0,
        "warning_count": 0,
        "errors": [],
        "warnings": [],
    }

    # Check if ESLint config exists
    eslint_configs = [
        ".eslintrc.js",
        ".eslintrc.json",
        ".eslintrc.yml",
        ".eslintrc.yaml",
        "eslint.config.js",
        "eslint.config.mjs",
    ]
    has_eslint = any((project_dir / cfg).exists() for cfg in eslint_configs)

    if not has_eslint:
        # Also check package.json for eslintConfig
        pkg_json = project_dir / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                has_eslint = "eslintConfig" in pkg
            except Exception:
                pass

    if not has_eslint:
        logger.info("No ESLint config found, skipping ESLint check")
        return result

    try:
        # Run eslint with JSON format
        proc = subprocess.run(
            ["npx", "eslint", ".", "--format", "json", "--ext", ".ts,.tsx,.js,.jsx"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Parse JSON output
        try:
            eslint_results = json.loads(proc.stdout)
        except json.JSONDecodeError:
            logger.warning("Could not parse ESLint JSON output")
            return result

        for file_result in eslint_results:
            file_path = file_result.get("filePath", "")
            # Make path relative to project
            try:
                rel_path = str(Path(file_path).relative_to(project_dir))
            except ValueError:
                rel_path = file_path

            for msg in file_result.get("messages", []):
                severity = "HIGH" if msg.get("severity") == 2 else "MEDIUM"
                finding = {
                    "ruleId": msg.get("ruleId", "unknown"),
                    "file": rel_path,
                    "line": msg.get("line", 0),
                    "column": msg.get("column", 0),
                    "message": msg.get("message", ""),
                    "severity": severity,
                }

                if msg.get("severity") == 2:  # Error
                    result["errors"].append(finding)
                else:  # Warning
                    result["warnings"].append(finding)

        result["error_count"] = len(result["errors"])
        result["warning_count"] = len(result["warnings"])
        result["passed"] = result["error_count"] == 0

    except subprocess.TimeoutExpired:
        logger.warning("ESLint check timed out")
    except FileNotFoundError:
        logger.warning("npx/eslint not found, skipping ESLint check")
    except Exception as e:
        logger.warning(f"ESLint check failed: {e}")

    return result


def _check_naming_conventions(project_dir: Path) -> dict:
    """Check for naming convention violations.

    Args:
        project_dir: Project directory path

    Returns:
        Dict with naming convention check results
    """
    result = {
        "passed": True,
        "violation_count": 0,
        "violations": [],
    }

    # Find all TypeScript/JavaScript files
    src_dir = project_dir / "src"
    if not src_dir.exists():
        src_dir = project_dir

    ts_files = list(src_dir.glob("**/*.ts")) + list(src_dir.glob("**/*.tsx"))
    ts_files += list(src_dir.glob("**/*.js")) + list(src_dir.glob("**/*.jsx"))

    # Patterns for checking
    pascal_case = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
    camel_case = re.compile(r"^[a-z][a-zA-Z0-9]*$")
    upper_snake = re.compile(r"^[A-Z][A-Z0-9_]*$")
    kebab_case = re.compile(r"^[a-z][a-z0-9-]*$")

    for file_path in ts_files[:100]:  # Limit to 100 files
        try:
            rel_path = file_path.relative_to(project_dir)
            file_name = file_path.stem

            # Check file name (should be kebab-case or camelCase for components)
            is_component = file_path.suffix in [".tsx", ".jsx"]

            if is_component:
                # React components can be PascalCase
                if not (pascal_case.match(file_name) or kebab_case.match(file_name)):
                    # Check if it's an index file
                    if file_name.lower() not in ["index", "app", "main"]:
                        result["violations"].append(
                            {
                                "file": str(rel_path),
                                "issue": "Component file should be PascalCase or kebab-case",
                                "expected": f"{file_name.replace('_', '-').lower()}.tsx or {file_name.title().replace('_', '')}.tsx",
                                "actual": f"{file_name}{file_path.suffix}",
                                "severity": "LOW",
                            }
                        )
            else:
                # Non-component files should be kebab-case
                if not kebab_case.match(file_name) and "_" in file_name:
                    result["violations"].append(
                        {
                            "file": str(rel_path),
                            "issue": "File name should use kebab-case, not snake_case",
                            "expected": file_name.replace("_", "-"),
                            "actual": file_name,
                            "severity": "LOW",
                        }
                    )

            # Check directory names (should be lowercase)
            for parent in rel_path.parents:
                parent_name = parent.name
                if (
                    parent_name
                    and parent_name[0].isupper()
                    and parent_name not in ["Documents", "Docs"]
                ):
                    result["violations"].append(
                        {
                            "file": str(rel_path),
                            "issue": "Directory name should be lowercase",
                            "expected": parent_name.lower(),
                            "actual": parent_name,
                            "severity": "MEDIUM",
                        }
                    )
                    break  # Only report once per file

        except Exception as e:
            logger.debug(f"Error checking {file_path}: {e}")

    result["violation_count"] = len(result["violations"])
    result["passed"] = result["violation_count"] == 0

    return result


def _check_code_structure(project_dir: Path, config: Any) -> dict:
    """Check code structure (file/function length).

    Args:
        project_dir: Project directory path
        config: Quality gate configuration

    Returns:
        Dict with code structure check results
    """
    result = {
        "passed": True,
        "issue_count": 0,
        "issues": [],
    }

    max_file_lines = config.quality_gate.max_file_lines
    max_function_lines = config.quality_gate.max_function_lines

    # Find all source files
    src_dir = project_dir / "src"
    if not src_dir.exists():
        src_dir = project_dir

    source_files = list(src_dir.glob("**/*.ts")) + list(src_dir.glob("**/*.tsx"))
    source_files += list(src_dir.glob("**/*.py"))

    for file_path in source_files[:50]:  # Limit to 50 files
        try:
            rel_path = str(file_path.relative_to(project_dir))
            content = file_path.read_text()
            lines = content.split("\n")
            line_count = len(lines)

            # Check file length
            if line_count > max_file_lines:
                result["issues"].append(
                    {
                        "type": "file_too_long",
                        "file": rel_path,
                        "lines": line_count,
                        "limit": max_file_lines,
                        "severity": "MEDIUM",
                    }
                )

            # Simple function length detection (TypeScript/JavaScript)
            if file_path.suffix in [".ts", ".tsx", ".js", ".jsx"]:
                func_pattern = re.compile(
                    r"(?:async\s+)?(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*\w+)?\s*=>)",
                    re.MULTILINE,
                )

                # Track brace depth for function boundaries
                in_function = False
                function_name = None
                function_start = 0
                brace_depth = 0

                for i, line in enumerate(lines):
                    # Detect function start
                    match = func_pattern.search(line)
                    if match and not in_function:
                        function_name = match.group(1) or match.group(2)
                        function_start = i
                        brace_depth = line.count("{") - line.count("}")
                        if brace_depth > 0:
                            in_function = True
                    elif in_function:
                        brace_depth += line.count("{") - line.count("}")
                        if brace_depth <= 0:
                            # Function ended
                            func_length = i - function_start + 1
                            if func_length > max_function_lines:
                                result["issues"].append(
                                    {
                                        "type": "function_too_long",
                                        "file": rel_path,
                                        "function": function_name,
                                        "lines": func_length,
                                        "limit": max_function_lines,
                                        "severity": "MEDIUM",
                                    }
                                )
                            in_function = False
                            function_name = None

        except Exception as e:
            logger.debug(f"Error checking structure of {file_path}: {e}")

    result["issue_count"] = len(result["issues"])
    # Structure issues are non-blocking
    result["passed"] = True

    return result


def _calculate_score(findings: list, base_score: float = 10.0) -> float:
    """Calculate quality score based on findings.

    Args:
        findings: List of findings with severity
        base_score: Starting score

    Returns:
        Calculated score (minimum 1.0)
    """
    score = base_score

    for finding in findings:
        severity = finding.get("severity", "INFO")
        deduction = SEVERITY_WEIGHTS.get(severity, 0)
        score -= deduction

    return max(1.0, score)


def _aggregate_findings(
    ts_result: dict,
    eslint_result: dict,
    naming_result: dict,
    structure_result: dict,
) -> list:
    """Aggregate findings from all checks.

    Args:
        ts_result: TypeScript check results
        eslint_result: ESLint check results
        naming_result: Naming convention results
        structure_result: Code structure results

    Returns:
        List of all findings
    """
    findings = []

    # TypeScript errors
    for error in ts_result.get("errors", []):
        findings.append(
            {
                "severity": error.get("severity", "MEDIUM"),
                "type": "TS_ERROR",
                "file": error.get("file", ""),
                "line": error.get("line", 0),
                "column": error.get("column", 0),
                "code": error.get("code", ""),
                "description": error.get("message", ""),
                "remediation": f"Fix TypeScript error {error.get('code', '')}",
            }
        )

    # ESLint errors
    for error in eslint_result.get("errors", []):
        findings.append(
            {
                "severity": "HIGH",
                "type": "ESLINT_ERROR",
                "file": error.get("file", ""),
                "line": error.get("line", 0),
                "column": error.get("column", 0),
                "code": error.get("ruleId", ""),
                "description": error.get("message", ""),
                "remediation": f"Fix ESLint rule: {error.get('ruleId', '')}",
            }
        )

    # ESLint warnings
    for warning in eslint_result.get("warnings", []):
        findings.append(
            {
                "severity": "MEDIUM",
                "type": "ESLINT_WARNING",
                "file": warning.get("file", ""),
                "line": warning.get("line", 0),
                "description": warning.get("message", ""),
                "remediation": f"Consider fixing: {warning.get('ruleId', '')}",
            }
        )

    # Naming violations
    for violation in naming_result.get("violations", []):
        findings.append(
            {
                "severity": violation.get("severity", "LOW"),
                "type": "NAMING_VIOLATION",
                "file": violation.get("file", ""),
                "line": 0,
                "description": violation.get("issue", ""),
                "remediation": f"Rename to: {violation.get('expected', '')}",
            }
        )

    # Structure issues
    for issue in structure_result.get("issues", []):
        findings.append(
            {
                "severity": issue.get("severity", "MEDIUM"),
                "type": "STRUCTURE_ISSUE",
                "file": issue.get("file", ""),
                "line": 0,
                "description": f"{issue.get('type', '')}: {issue.get('lines', 0)} lines (limit: {issue.get('limit', 0)})",
                "remediation": "Consider refactoring to reduce complexity",
            }
        )

    return findings


async def quality_gate_node(state: WorkflowState) -> dict[str, Any]:
    """Run quality gate checks.

    Args:
        state: Current workflow state

    Returns:
        State updates with quality gate results
    """
    project_dir = Path(state["project_dir"])
    logger.info(f"Running quality gate for: {state['project_name']}")

    # Load project config
    config = load_project_config(project_dir)

    # Check if feature is enabled
    if not config.workflow.features.quality_gate:
        logger.info("Quality gate disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    if not config.quality_gate.enabled:
        logger.info("Quality gate disabled in config, skipping")
        return {
            "updated_at": datetime.now().isoformat(),
            "next_decision": "continue",
        }

    # Run all checks
    ts_result = (
        _run_typescript_check(project_dir)
        if config.quality_gate.typescript_strict
        else {"passed": True, "error_count": 0, "errors": []}
    )
    eslint_result = (
        _run_eslint_check(project_dir)
        if config.quality_gate.eslint_required
        else {"passed": True, "error_count": 0, "warning_count": 0, "errors": [], "warnings": []}
    )
    naming_result = (
        _check_naming_conventions(project_dir)
        if config.quality_gate.naming_conventions
        else {"passed": True, "violation_count": 0, "violations": []}
    )
    structure_result = (
        _check_code_structure(project_dir, config)
        if config.quality_gate.code_structure
        else {"passed": True, "issue_count": 0, "issues": []}
    )

    # Aggregate findings
    findings = _aggregate_findings(ts_result, eslint_result, naming_result, structure_result)

    # Calculate score
    score = _calculate_score(findings)

    # Determine blocking issues
    blocking_issues = []
    blocking_severities = config.quality_gate.blocking_severities

    if ts_result.get("error_count", 0) > 0:
        blocking_issues.append(f"{ts_result['error_count']} TypeScript errors must be fixed")

    if eslint_result.get("error_count", 0) > 0:
        blocking_issues.append(f"{eslint_result['error_count']} ESLint errors must be fixed")

    # Overall pass/fail
    passed = len(blocking_issues) == 0 and score >= config.quality_gate.minimum_score

    # Build result
    quality_gate_result = {
        "agent": "A13",
        "task_id": "quality-gate",
        "status": "passed" if passed else "failed",
        "passed": passed,
        "score": round(score, 1),
        "checks": {
            "typescript": ts_result,
            "eslint": eslint_result,
            "naming_conventions": naming_result,
            "code_structure": structure_result,
        },
        "findings": findings[:50],  # Limit to 50 findings
        "blocking_issues": blocking_issues,
        "summary": (
            f"Quality gate {'passed' if passed else 'failed'}. "
            f"Score: {score:.1f}/10. "
            f"{ts_result.get('error_count', 0)} TS errors, "
            f"{eslint_result.get('error_count', 0)} ESLint errors, "
            f"{naming_result.get('violation_count', 0)} naming violations, "
            f"{structure_result.get('issue_count', 0)} structure issues."
        ),
        "timestamp": datetime.now().isoformat(),
    }

    # Save results to database
    from ...db.repositories.phase_outputs import get_phase_output_repository
    from ...storage.async_utils import run_async

    repo = get_phase_output_repository(state["project_name"])
    run_async(repo.save_output(phase=4, output_type="quality_gate", content=quality_gate_result))

    logger.info(
        f"Quality gate {'passed' if passed else 'failed'}: "
        f"score={score:.1f}, TS errors={ts_result.get('error_count', 0)}, "
        f"ESLint errors={eslint_result.get('error_count', 0)}"
    )

    if not passed:
        # Create error context for failed quality gate
        error_ctx = create_error_context(
            source_node="quality_gate",
            exception=Exception(f"Quality gate failed: {', '.join(blocking_issues)}"),
            state=state,
            recoverable=True,
            suggested_actions=[
                "Fix TypeScript type errors",
                "Fix ESLint rule violations",
                "Run 'npm run lint -- --fix' for auto-fixable issues",
            ],
        )

        return {
            "quality_gate_result": quality_gate_result,
            "errors": [error_ctx],
            "next_decision": "retry",  # Retry implementation to fix issues
            "updated_at": datetime.now().isoformat(),
        }

    return {
        "quality_gate_result": quality_gate_result,
        "updated_at": datetime.now().isoformat(),
        "next_decision": "continue",
    }
