"""Extended tests for the validator module."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_forge.validator import (
    ValidationIssue,
    ValidationReport,
    validate_initialize_response,
    validate_project_structure,
    validate_tool_definitions,
    validate_tool_result,
)


class TestValidationReport:
    def test_empty_report_is_valid(self) -> None:
        report = ValidationReport()
        assert report.is_valid
        assert report.errors == []
        assert report.warnings == []

    def test_add_error(self) -> None:
        report = ValidationReport()
        report.add_error("test", "Something broke")
        assert not report.is_valid
        assert len(report.errors) == 1
        assert report.errors[0].message == "Something broke"

    def test_add_warning(self) -> None:
        report = ValidationReport()
        report.add_warning("test", "Heads up")
        assert report.is_valid  # Warnings don't invalidate
        assert len(report.warnings) == 1

    def test_mixed_issues(self) -> None:
        report = ValidationReport()
        report.add_error("a", "error1")
        report.add_warning("b", "warning1")
        report.add_error("c", "error2")
        assert not report.is_valid
        assert len(report.errors) == 2
        assert len(report.warnings) == 1
        assert len(report.issues) == 3


class TestValidationIssue:
    def test_issue_fields(self) -> None:
        issue = ValidationIssue(level="error", category="structure", message="Missing file")
        assert issue.level == "error"
        assert issue.category == "structure"
        assert issue.message == "Missing file"


class TestValidateProjectStructure:
    def test_empty_dir_fails(self, tmp_path: Path) -> None:
        report = validate_project_structure(tmp_path)
        assert not report.is_valid

    def test_no_src_dir(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        report = validate_project_structure(tmp_path)
        assert not report.is_valid
        assert any("src" in e.message for e in report.errors)

    def test_empty_src_dir(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        (tmp_path / "src").mkdir()
        report = validate_project_structure(tmp_path)
        assert not report.is_valid
        assert any("No Python package" in e.message for e in report.errors)

    def test_missing_server_py(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        pkg = tmp_path / "src" / "my_pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "tools.py").write_text("")
        report = validate_project_structure(tmp_path)
        assert not report.is_valid
        assert any("server.py" in e.message for e in report.errors)

    def test_missing_tools_py(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        pkg = tmp_path / "src" / "my_pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "server.py").write_text("")
        report = validate_project_structure(tmp_path)
        assert not report.is_valid
        assert any("tools.py" in e.message for e in report.errors)

    def test_valid_structure(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        (tmp_path / "README.md").write_text("# Test")
        (tmp_path / "Dockerfile").write_text("FROM python:3.12")
        (tmp_path / ".gitignore").write_text("*.pyc")
        pkg = tmp_path / "src" / "my_pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "server.py").write_text("")
        (pkg / "tools.py").write_text("")
        report = validate_project_structure(tmp_path)
        assert report.is_valid

    def test_warnings_for_missing_recommended(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        pkg = tmp_path / "src" / "my_pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "server.py").write_text("")
        (pkg / "tools.py").write_text("")
        report = validate_project_structure(tmp_path)
        assert report.is_valid  # Warnings don't fail
        assert len(report.warnings) >= 1


class TestValidateToolDefinitions:
    def test_valid_single_tool(self) -> None:
        tools = [{
            "name": "search",
            "description": "Search the web",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }]
        report = validate_tool_definitions(tools)
        assert report.is_valid

    def test_multiple_valid_tools(self) -> None:
        tools = [
            {"name": "a", "description": "Tool A", "inputSchema": {"type": "object"}},
            {"name": "b", "description": "Tool B", "inputSchema": {"type": "object"}},
        ]
        report = validate_tool_definitions(tools)
        assert report.is_valid

    def test_missing_description(self) -> None:
        tools = [{"name": "x", "inputSchema": {"type": "object"}}]
        report = validate_tool_definitions(tools)
        assert not report.is_valid

    def test_missing_input_schema(self) -> None:
        tools = [{"name": "x", "description": "X tool"}]
        report = validate_tool_definitions(tools)
        assert not report.is_valid

    def test_empty_name(self) -> None:
        tools = [{"name": "", "description": "X", "inputSchema": {"type": "object"}}]
        report = validate_tool_definitions(tools)
        assert not report.is_valid

    def test_triple_duplicates(self) -> None:
        tools = [
            {"name": "x", "description": "A", "inputSchema": {"type": "object"}},
            {"name": "x", "description": "B", "inputSchema": {"type": "object"}},
            {"name": "x", "description": "C", "inputSchema": {"type": "object"}},
        ]
        report = validate_tool_definitions(tools)
        assert not report.is_valid
        # At least 2 duplicate errors (second and third)
        dup_errors = [e for e in report.errors if "Duplicate" in e.message]
        assert len(dup_errors) >= 2


class TestValidateInitializeResponse:
    def test_full_valid_response(self) -> None:
        resp = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "test-server", "version": "1.0.0"},
        }
        report = validate_initialize_response(resp)
        assert report.is_valid

    def test_missing_server_info(self) -> None:
        resp = {"protocolVersion": "2024-11-05", "capabilities": {}}
        report = validate_initialize_response(resp)
        assert not report.is_valid

    def test_missing_capabilities(self) -> None:
        resp = {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "test", "version": "1.0"},
        }
        report = validate_initialize_response(resp)
        assert not report.is_valid

    def test_missing_protocol_version(self) -> None:
        resp = {
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1.0"},
        }
        report = validate_initialize_response(resp)
        assert not report.is_valid

    def test_empty_response(self) -> None:
        report = validate_initialize_response({})
        assert not report.is_valid


class TestValidateToolResult:
    def test_valid_text_result(self) -> None:
        result = {"content": [{"type": "text", "text": "hello"}]}
        report = validate_tool_result(result)
        assert report.is_valid

    def test_valid_image_result(self) -> None:
        result = {"content": [{"type": "image", "data": "base64..."}]}
        report = validate_tool_result(result)
        assert report.is_valid

    def test_valid_with_is_error(self) -> None:
        result = {
            "content": [{"type": "text", "text": "error occurred"}],
            "isError": True,
        }
        report = validate_tool_result(result)
        assert report.is_valid

    def test_missing_content(self) -> None:
        report = validate_tool_result({})
        assert not report.is_valid

    def test_invalid_content_type(self) -> None:
        result = {"content": [{"type": "video"}]}
        report = validate_tool_result(result)
        assert not report.is_valid

    def test_empty_content_array(self) -> None:
        result = {"content": []}
        report = validate_tool_result(result)
        assert report.is_valid

    def test_multiple_content_items(self) -> None:
        result = {
            "content": [
                {"type": "text", "text": "first"},
                {"type": "text", "text": "second"},
            ]
        }
        report = validate_tool_result(result)
        assert report.is_valid
