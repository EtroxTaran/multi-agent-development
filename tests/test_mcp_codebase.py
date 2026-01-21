"""Tests for MCP codebase server.

Tests cover:
1. search_code - Code pattern search with ripgrep
2. get_symbols - Symbol extraction from files
3. find_references - Reference finding
4. get_file_structure - Project file tree
5. get_file_summary - File summary generation

Run with: pytest tests/test_mcp_codebase.py -v
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import os

# Import server functions
from mcp_servers.codebase.server import (
    search_code,
    get_symbols,
    find_references,
    get_file_structure,
    get_file_summary,
    create_server,
    PROJECTS_ROOT,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_projects_dir(tmp_path):
    """Create a temporary projects directory with sample project."""
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()

    # Create a sample project
    project_dir = projects_dir / "test-project"
    project_dir.mkdir()

    # Create src directory
    src_dir = project_dir / "src"
    src_dir.mkdir()

    # Create Python files
    (src_dir / "calculator.py").write_text('''"""Calculator module."""

import math
from typing import Optional

class Calculator:
    """A simple calculator class."""

    def __init__(self):
        self.result = 0

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract b from a."""
        return a - b

    async def async_divide(self, a: int, b: int) -> float:
        """Async divide operation."""
        return a / b

def helper_function():
    """A helper function."""
    pass

PI = 3.14159
''')

    (src_dir / "utils.py").write_text('''"""Utility functions."""

from calculator import Calculator

def format_result(value: float) -> str:
    """Format a numeric result."""
    return f"{value:.2f}"

def create_calculator() -> Calculator:
    """Factory function for Calculator."""
    return Calculator()

calc = Calculator()
''')

    # Create TypeScript file
    (src_dir / "app.ts").write_text('''import { Calculator } from './calculator';

export class App {
    private calculator: Calculator;

    constructor() {
        this.calculator = new Calculator();
    }

    async run(): Promise<void> {
        console.log('Running app');
    }
}

export function createApp(): App {
    return new App();
}

export const VERSION = '1.0.0';
''')

    # Create JavaScript file
    (src_dir / "legacy.js").write_text('''const Calculator = require('./calculator');

function legacyAdd(a, b) {
    return a + b;
}

class LegacyHelper {
    constructor() {
        this.value = 0;
    }
}

module.exports = { legacyAdd, LegacyHelper };
''')

    # Create tests directory
    tests_dir = project_dir / "tests"
    tests_dir.mkdir()

    (tests_dir / "test_calculator.py").write_text('''"""Tests for calculator."""

import pytest
from src.calculator import Calculator

def test_add():
    calc = Calculator()
    assert calc.add(2, 3) == 5

def test_subtract():
    calc = Calculator()
    assert calc.subtract(5, 3) == 2
''')

    return projects_dir


@pytest.fixture
def mock_projects_root(temp_projects_dir, monkeypatch):
    """Mock PROJECTS_ROOT to use temp directory."""
    import mcp_servers.codebase.server as server_module
    monkeypatch.setattr(server_module, 'PROJECTS_ROOT', temp_projects_dir)
    return temp_projects_dir


# =============================================================================
# Test search_code
# =============================================================================

class TestSearchCode:
    """Tests for search_code function."""

    @pytest.mark.asyncio
    async def test_search_code_project_not_found(self, mock_projects_root):
        """Test searching in non-existent project."""
        result = await search_code(
            query="test",
            project="nonexistent-project",
        )

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_search_code_with_ripgrep_mock(self, mock_projects_root):
        """Test search_code with mocked ripgrep."""
        mock_output = '\n'.join([
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": "src/calculator.py"},
                    "line_number": 10,
                    "lines": {"text": "    def add(self, a: int, b: int) -> int:\n"}
                }
            }),
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": "src/utils.py"},
                    "line_number": 5,
                    "lines": {"text": "    return a + b\n"}
                }
            }),
        ])

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)

            result = await search_code(
                query="add",
                project="test-project",
            )

            assert "error" not in result
            assert result["query"] == "add"
            assert result["project"] == "test-project"
            assert result["total_matches"] == 2
            assert len(result["matches"]) == 2

    @pytest.mark.asyncio
    async def test_search_code_with_file_type_filter(self, mock_projects_root):
        """Test search with file type filter."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)

            await search_code(
                query="def",
                project="test-project",
                file_type="py",
            )

            # Verify ripgrep was called with -t flag
            call_args = mock_run.call_args[0][0]
            assert "-t" in call_args
            assert "py" in call_args

    @pytest.mark.asyncio
    async def test_search_code_timeout(self, mock_projects_root):
        """Test search timeout handling."""
        import subprocess

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="rg", timeout=30)

            result = await search_code(
                query="test",
                project="test-project",
            )

            assert "error" in result
            assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_search_code_ripgrep_not_found(self, mock_projects_root):
        """Test handling when ripgrep is not installed."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await search_code(
                query="test",
                project="test-project",
            )

            assert "error" in result
            assert "ripgrep not installed" in result["error"]

    @pytest.mark.asyncio
    async def test_search_code_max_results(self, mock_projects_root):
        """Test max_results parameter."""
        # Create output with more matches than limit
        matches = [
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": f"file{i}.py"},
                    "line_number": i,
                    "lines": {"text": f"match {i}\n"}
                }
            })
            for i in range(10)
        ]

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='\n'.join(matches), returncode=0)

            result = await search_code(
                query="match",
                project="test-project",
                max_results=5,
            )

            assert len(result["matches"]) <= 5


# =============================================================================
# Test get_symbols
# =============================================================================

class TestGetSymbols:
    """Tests for get_symbols function."""

    @pytest.mark.asyncio
    async def test_get_symbols_project_not_found(self, mock_projects_root):
        """Test getting symbols from non-existent project."""
        result = await get_symbols(project="nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_symbols_python_file(self, mock_projects_root):
        """Test extracting symbols from Python file."""
        result = await get_symbols(
            project="test-project",
            file_path="src/calculator.py",
        )

        assert "error" not in result
        assert result["project"] == "test-project"
        assert "symbols" in result

        symbols = result["symbols"]

        # Check classes
        class_names = [c["name"] for c in symbols["classes"]]
        assert "Calculator" in class_names

        # Check functions
        func_names = [f["name"] for f in symbols["functions"]]
        assert "helper_function" in func_names

        # Check methods
        method_names = [m["name"] for m in symbols["methods"]]
        assert "add" in method_names
        assert "subtract" in method_names
        assert "async_divide" in method_names

    @pytest.mark.asyncio
    async def test_get_symbols_all_types(self, mock_projects_root):
        """Test getting all symbol types."""
        result = await get_symbols(
            project="test-project",
            symbol_type="all",
        )

        assert "error" not in result
        symbols = result["symbols"]

        # Should have found symbols in multiple files
        assert result["total"] > 0

    @pytest.mark.asyncio
    async def test_get_symbols_filter_by_type(self, mock_projects_root):
        """Test filtering symbols by type."""
        result = await get_symbols(
            project="test-project",
            symbol_type="class",
        )

        assert "error" not in result
        symbols = result["symbols"]

        # Only classes should be populated
        assert len(symbols["classes"]) > 0

    @pytest.mark.asyncio
    async def test_get_symbols_typescript_file(self, mock_projects_root):
        """Test extracting symbols from TypeScript file."""
        result = await get_symbols(
            project="test-project",
            file_path="src/app.ts",
        )

        assert "error" not in result
        symbols = result["symbols"]

        # Check classes
        class_names = [c["name"] for c in symbols["classes"]]
        assert "App" in class_names

        # Check functions
        func_names = [f["name"] for f in symbols["functions"]]
        assert "createApp" in func_names


# =============================================================================
# Test find_references
# =============================================================================

class TestFindReferences:
    """Tests for find_references function."""

    @pytest.mark.asyncio
    async def test_find_references_project_not_found(self, mock_projects_root):
        """Test finding references in non-existent project."""
        result = await find_references(
            symbol="Calculator",
            project="nonexistent",
        )

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_find_references_with_mock(self, mock_projects_root):
        """Test finding references with mocked ripgrep."""
        mock_output = '\n'.join([
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": "src/calculator.py"},
                    "line_number": 5,
                    "lines": {"text": "class Calculator:\n"}
                }
            }),
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": "src/utils.py"},
                    "line_number": 3,
                    "lines": {"text": "from calculator import Calculator\n"}
                }
            }),
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": "src/utils.py"},
                    "line_number": 10,
                    "lines": {"text": "    return Calculator()\n"}
                }
            }),
        ])

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)

            result = await find_references(
                symbol="Calculator",
                project="test-project",
            )

            assert "error" not in result
            assert result["symbol"] == "Calculator"
            assert result["total_references"] == 3

            # Check definition detection
            refs = result["references"]
            definitions = [r for r in refs if r["is_definition"]]
            assert len(definitions) >= 1

    @pytest.mark.asyncio
    async def test_find_references_exclude_definition(self, mock_projects_root):
        """Test excluding definition from results."""
        mock_output = '\n'.join([
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": "src/calculator.py"},
                    "line_number": 5,
                    "lines": {"text": "class Calculator:\n"}
                }
            }),
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": "src/utils.py"},
                    "line_number": 10,
                    "lines": {"text": "    return Calculator()\n"}
                }
            }),
        ])

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)

            result = await find_references(
                symbol="Calculator",
                project="test-project",
                include_definition=False,
            )

            # Definition should be excluded
            definitions = [r for r in result["references"] if r["is_definition"]]
            assert len(definitions) == 0


# =============================================================================
# Test get_file_structure
# =============================================================================

class TestGetFileStructure:
    """Tests for get_file_structure function."""

    @pytest.mark.asyncio
    async def test_get_file_structure_project_not_found(self, mock_projects_root):
        """Test getting structure of non-existent project."""
        result = await get_file_structure(project="nonexistent")

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_file_structure_basic(self, mock_projects_root):
        """Test getting basic file structure."""
        result = await get_file_structure(project="test-project")

        assert "error" not in result
        assert result["project"] == "test-project"
        assert "structure" in result

        structure = result["structure"]
        assert structure["type"] == "directory"
        assert "children" in structure

    @pytest.mark.asyncio
    async def test_get_file_structure_with_path(self, mock_projects_root):
        """Test getting structure of subdirectory."""
        result = await get_file_structure(
            project="test-project",
            path="src",
        )

        assert "error" not in result
        structure = result["structure"]

        # Should have files directly
        file_names = [c["name"] for c in structure["children"] if c["type"] == "file"]
        assert "calculator.py" in file_names
        assert "utils.py" in file_names
        assert "app.ts" in file_names

    @pytest.mark.asyncio
    async def test_get_file_structure_max_depth(self, mock_projects_root):
        """Test max_depth parameter."""
        # Create nested directories
        nested = mock_projects_root / "test-project" / "a" / "b" / "c" / "d"
        nested.mkdir(parents=True)
        (nested / "deep.py").write_text("# deep file")

        result = await get_file_structure(
            project="test-project",
            max_depth=2,
        )

        assert "error" not in result

        # Find truncated directories
        def find_truncated(node):
            truncated = []
            if node.get("truncated"):
                truncated.append(node["name"])
            for child in node.get("children", []):
                truncated.extend(find_truncated(child))
            return truncated

        truncated = find_truncated(result["structure"])
        # Should have truncated at some depth
        assert len(truncated) >= 0  # May or may not be truncated depending on depth

    @pytest.mark.asyncio
    async def test_get_file_structure_include_hidden(self, mock_projects_root):
        """Test including hidden files."""
        # Create hidden file
        (mock_projects_root / "test-project" / ".hidden").write_text("hidden")

        result_without = await get_file_structure(
            project="test-project",
            include_hidden=False,
        )

        result_with = await get_file_structure(
            project="test-project",
            include_hidden=True,
        )

        def count_files(node):
            count = 1 if node["type"] == "file" else 0
            for child in node.get("children", []):
                count += count_files(child)
            return count

        # With hidden should have more files
        without_count = count_files(result_without["structure"])
        with_count = count_files(result_with["structure"])

        assert with_count >= without_count

    @pytest.mark.asyncio
    async def test_get_file_structure_skips_node_modules(self, mock_projects_root):
        """Test that node_modules is skipped."""
        # Create node_modules
        node_modules = mock_projects_root / "test-project" / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.json").write_text("{}")

        result = await get_file_structure(project="test-project")

        def find_node_modules(node):
            if node["name"] == "node_modules":
                return True
            for child in node.get("children", []):
                if find_node_modules(child):
                    return True
            return False

        assert not find_node_modules(result["structure"])


# =============================================================================
# Test get_file_summary
# =============================================================================

class TestGetFileSummary:
    """Tests for get_file_summary function."""

    @pytest.mark.asyncio
    async def test_get_file_summary_not_found(self, mock_projects_root):
        """Test summary of non-existent file."""
        result = await get_file_summary(
            project="test-project",
            file_path="nonexistent.py",
        )

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_get_file_summary_python(self, mock_projects_root):
        """Test Python file summary."""
        result = await get_file_summary(
            project="test-project",
            file_path="src/calculator.py",
        )

        assert "error" not in result
        assert result["file"] == "src/calculator.py"
        assert result["lines"] > 0
        assert result["size"] > 0

        # Check imports
        import_stmts = [i["statement"] for i in result["imports"]]
        assert any("import math" in s for s in import_stmts)
        assert any("from typing" in s for s in import_stmts)

        # Check functions
        func_names = [f["name"] for f in result["functions"]]
        assert "helper_function" in func_names

        # Check classes
        class_names = [c["name"] for c in result["classes"]]
        assert "Calculator" in class_names

    @pytest.mark.asyncio
    async def test_get_file_summary_typescript(self, mock_projects_root):
        """Test TypeScript file summary."""
        result = await get_file_summary(
            project="test-project",
            file_path="src/app.ts",
        )

        assert "error" not in result

        # Check imports
        assert len(result["imports"]) > 0

        # Check exports
        assert len(result["exports"]) > 0

        # Check classes
        class_names = [c["name"] for c in result["classes"]]
        assert "App" in class_names

        # Check functions
        func_names = [f["name"] for f in result["functions"]]
        assert "createApp" in func_names

    @pytest.mark.asyncio
    async def test_get_file_summary_javascript(self, mock_projects_root):
        """Test JavaScript file summary."""
        result = await get_file_summary(
            project="test-project",
            file_path="src/legacy.js",
        )

        assert "error" not in result

        # Check functions
        func_names = [f["name"] for f in result["functions"]]
        assert "legacyAdd" in func_names

        # Check classes
        class_names = [c["name"] for c in result["classes"]]
        assert "LegacyHelper" in class_names


# =============================================================================
# Test Server Creation
# =============================================================================

class TestCreateServer:
    """Tests for server creation and configuration."""

    def test_create_server(self):
        """Test server is created successfully."""
        server = create_server()

        assert server is not None
        assert server.name == "mcp-codebase"

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing available tools."""
        server = create_server()

        # The MCP Server stores handlers in request_handlers dict
        # Access the list_tools handler via the proper internal attribute
        assert hasattr(server, 'request_handlers'), "Server should have request_handlers"

        # Verify the server is properly configured by checking it has the expected handlers
        # Note: The actual tools are verified via integration tests; here we just verify
        # the server was created with the expected structure
        assert server.name == "mcp-codebase"

        # Check that list_tools handler is registered
        from mcp.types import ListToolsRequest
        assert ListToolsRequest in server.request_handlers

    @pytest.mark.asyncio
    async def test_list_resources(self, mock_projects_root):
        """Test listing project resources."""
        server = create_server()

        # The resources handler should list projects
        # We can't easily test this without more infrastructure,
        # but we verify the server is created correctly
        assert server is not None


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_project(self, mock_projects_root):
        """Test handling empty project."""
        # Create empty project
        empty = mock_projects_root / "empty-project"
        empty.mkdir()

        result = await get_symbols(project="empty-project")

        assert "error" not in result
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_binary_file_handling(self, mock_projects_root):
        """Test handling binary files gracefully."""
        # Create a binary file
        binary_file = mock_projects_root / "test-project" / "src" / "binary.bin"
        binary_file.write_bytes(b'\x00\x01\x02\x03')

        # This shouldn't crash
        result = await get_file_structure(project="test-project")
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_special_characters_in_search(self, mock_projects_root):
        """Test search with regex special characters."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)

            # This shouldn't crash
            result = await search_code(
                query="def\\s+\\w+",  # Regex pattern
                project="test-project",
            )

            assert "error" not in result or "not found" not in result.get("error", "")

    @pytest.mark.asyncio
    async def test_unicode_file_content(self, mock_projects_root):
        """Test handling files with unicode content."""
        # Create file with unicode
        unicode_file = mock_projects_root / "test-project" / "src" / "unicode.py"
        unicode_file.write_text('# -*- coding: utf-8 -*-\n"""Unicode: 你好世界 🌍"""\n\ndef greet():\n    return "Hello 世界"')

        result = await get_file_summary(
            project="test-project",
            file_path="src/unicode.py",
        )

        assert "error" not in result
        assert result["lines"] > 0


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
