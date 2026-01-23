"""Tests for Ralph Wiggum loop integration.

Tests cover:
1. RalphLoopConfig defaults
2. Test framework detection
3. Loop execution logic
4. Completion detection
5. Iteration context building

Run with: pytest tests/test_ralph_loop.py -v
"""

import json

import pytest

from orchestrator.langgraph.integrations.ralph_loop import (
    COMPLETION_PROMISE,
    RalphLoopConfig,
    RalphLoopResult,
    _build_previous_context,
    _extract_test_summary,
    _format_criteria,
    _format_list,
    _parse_iteration_output,
    detect_test_framework,
)

# =============================================================================
# Test RalphLoopConfig
# =============================================================================


class TestRalphLoopConfig:
    """Test Ralph loop configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RalphLoopConfig()

        assert config.max_iterations == 10
        assert config.iteration_timeout == 300
        assert config.test_command == "pytest"
        assert config.completion_pattern == COMPLETION_PROMISE
        assert "Read" in config.allowed_tools
        assert "Write" in config.allowed_tools
        assert config.max_turns_per_iteration == 15
        assert config.save_iteration_logs is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = RalphLoopConfig(
            max_iterations=5,
            iteration_timeout=120,
            test_command="npm test",
        )

        assert config.max_iterations == 5
        assert config.iteration_timeout == 120
        assert config.test_command == "npm test"


# =============================================================================
# Test RalphLoopResult
# =============================================================================


class TestRalphLoopResult:
    """Test Ralph loop result dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = RalphLoopResult(
            success=True,
            iterations=3,
            final_output={"status": "completed"},
            total_time_seconds=45.5,
            completion_reason="all_tests_passed",
        )

        assert result.success is True
        assert result.iterations == 3
        assert result.completion_reason == "all_tests_passed"

    def test_failure_result(self):
        """Test failure result."""
        result = RalphLoopResult(
            success=False,
            iterations=10,
            completion_reason="max_iterations_reached",
            error="Failed after 10 iterations",
        )

        assert result.success is False
        assert result.error is not None

    def test_to_dict(self):
        """Test conversion to dict."""
        result = RalphLoopResult(
            success=True,
            iterations=2,
            completion_reason="completion_promise_detected",
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["iterations"] == 2
        assert data["completion_reason"] == "completion_promise_detected"


# =============================================================================
# Test Test Framework Detection
# =============================================================================


class TestDetectTestFramework:
    """Test test framework detection."""

    def test_detect_pytest(self, temp_project_dir):
        """Test detecting pytest."""
        (temp_project_dir / "pytest.ini").write_text("[pytest]\n")

        result = detect_test_framework(temp_project_dir)

        assert result == "pytest"

    def test_detect_pytest_pyproject(self, temp_project_dir):
        """Test detecting pytest via pyproject.toml."""
        (temp_project_dir / "pyproject.toml").write_text("[tool.pytest]\n")

        result = detect_test_framework(temp_project_dir)

        assert result == "pytest"

    def test_detect_bun(self, temp_project_dir):
        """Test detecting bun test."""
        (temp_project_dir / "package.json").write_text(
            json.dumps({"devDependencies": {"bun": "^1.0.0"}})
        )

        result = detect_test_framework(temp_project_dir)

        assert result == "bun test"

    def test_detect_jest(self, temp_project_dir):
        """Test detecting jest via npm."""
        (temp_project_dir / "package.json").write_text(
            json.dumps({"devDependencies": {"jest": "^29.0.0"}})
        )

        result = detect_test_framework(temp_project_dir)

        assert result == "npm test"

    def test_detect_vitest(self, temp_project_dir):
        """Test detecting vitest via npm."""
        (temp_project_dir / "package.json").write_text(
            json.dumps({"devDependencies": {"vitest": "^1.0.0"}})
        )

        result = detect_test_framework(temp_project_dir)

        assert result == "npm test"

    def test_detect_cargo(self, temp_project_dir):
        """Test detecting cargo test."""
        (temp_project_dir / "Cargo.toml").write_text("[package]\n")

        result = detect_test_framework(temp_project_dir)

        assert result == "cargo test"

    def test_detect_go(self, temp_project_dir):
        """Test detecting go test."""
        (temp_project_dir / "go.mod").write_text("module test\n")

        result = detect_test_framework(temp_project_dir)

        assert result == "go test"

    def test_default_pytest(self, temp_project_dir):
        """Test default to pytest when no config found."""
        result = detect_test_framework(temp_project_dir)

        assert result == "pytest"


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Test helper formatting functions."""

    def test_format_criteria_empty(self):
        """Test formatting empty criteria."""
        result = _format_criteria([])

        assert "No specific criteria" in result

    def test_format_criteria_list(self):
        """Test formatting criteria list."""
        result = _format_criteria(["Can add numbers", "Can subtract"])

        assert "- [ ] Can add numbers" in result
        assert "- [ ] Can subtract" in result

    def test_format_list_empty(self):
        """Test formatting empty list."""
        result = _format_list([])

        assert "None specified" in result

    def test_format_list_items(self):
        """Test formatting list items."""
        result = _format_list(["file1.py", "file2.py"])

        assert "- file1.py" in result
        assert "- file2.py" in result


# =============================================================================
# Test Output Parsing
# =============================================================================


class TestOutputParsing:
    """Test iteration output parsing."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON output."""
        output = '{"status": "completed", "files_created": ["test.py"]}'

        result = _parse_iteration_output(output)

        assert result["status"] == "completed"
        assert "test.py" in result["files_created"]

    def test_parse_empty_output(self):
        """Test parsing empty output."""
        result = _parse_iteration_output("")

        assert result == {}

    def test_parse_json_in_text(self):
        """Test extracting JSON from text output."""
        output = """
        Some text before
        {"status": "completed"}
        Some text after
        """

        result = _parse_iteration_output(output)

        assert result.get("status") == "completed"

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns raw output."""
        output = "This is not JSON"

        result = _parse_iteration_output(output)

        assert "raw_output" in result


# =============================================================================
# Test Context Building
# =============================================================================


class TestContextBuilding:
    """Test previous iteration context building."""

    def test_build_context_with_changes(self):
        """Test building context with file changes."""
        test_result = {
            "all_passed": False,
            "summary": "2 passed, 3 failed",
        }

        context = _build_previous_context(
            iteration=1,
            test_result=test_result,
            changes_made=["src/calc.py"],
        )

        assert "PREVIOUS ITERATION 1" in context
        assert "src/calc.py" in context
        assert "2 passed, 3 failed" in context
        assert "still failing" in context

    def test_build_context_tests_passed(self):
        """Test context when tests pass."""
        test_result = {
            "all_passed": True,
            "summary": "5 passed",
        }

        context = _build_previous_context(
            iteration=2,
            test_result=test_result,
            changes_made=[],
        )

        assert "still failing" not in context


# =============================================================================
# Test Summary Extraction
# =============================================================================


class TestSummaryExtraction:
    """Test test summary extraction."""

    def test_extract_pytest_summary(self):
        """Test extracting pytest summary."""
        output = """
        test_calc.py::test_add PASSED
        test_calc.py::test_sub FAILED
        ===== 1 passed, 1 failed in 0.05s =====
        """

        summary = _extract_test_summary(output)

        assert "1 passed" in summary
        assert "1 failed" in summary

    def test_extract_passed_count(self):
        """Test extracting PASSED count."""
        output = """
        PASSED test_one
        PASSED test_two
        FAILED test_three
        """

        summary = _extract_test_summary(output)

        assert "2 passed" in summary
        assert "1 failed" in summary

    def test_no_summary_available(self):
        """Test when no summary found."""
        output = "Some random output"

        summary = _extract_test_summary(output)

        assert "No test summary" in summary


# =============================================================================
# Test Completion Promise
# =============================================================================


class TestCompletionPromise:
    """Test completion promise detection."""

    def test_completion_promise_constant(self):
        """Test completion promise is defined."""
        assert COMPLETION_PROMISE == "<promise>DONE</promise>"

    def test_completion_in_output(self):
        """Test detecting completion in output."""
        output = f"Task completed successfully. {COMPLETION_PROMISE}"

        assert COMPLETION_PROMISE in output


# =============================================================================
# Test Integration Exports
# =============================================================================


class TestIntegrationExports:
    """Test Ralph loop is exported from integrations."""

    def test_exports(self):
        """Test Ralph loop classes are exported."""
        from orchestrator.langgraph.integrations import (
            COMPLETION_PROMISE,
            RalphLoopConfig,
            RalphLoopResult,
            detect_test_framework,
            run_ralph_loop,
        )

        assert RalphLoopConfig is not None
        assert RalphLoopResult is not None
        assert run_ralph_loop is not None
        assert detect_test_framework is not None
        assert COMPLETION_PROMISE is not None


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
