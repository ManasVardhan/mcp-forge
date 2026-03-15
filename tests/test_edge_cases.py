"""Edge case and error path tests for mcp-forge.

Covers input validation, resource schema validation, CLI error paths,
and boundary conditions not covered by other test files.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from mcp_forge.cli import cli
from mcp_forge.scaffold import (
    scaffold_project,
    snake_case,
    title_case,
    validate_project_name,
    validate_tool_names,
)
from mcp_forge.validator import (
    validate_resource_definitions,
    validate_tool_definitions,
)


# -- Project name validation --------------------------------------------------


class TestValidateProjectName:
    def test_valid_simple(self) -> None:
        validate_project_name("my-server")  # should not raise

    def test_valid_underscores(self) -> None:
        validate_project_name("my_server")

    def test_valid_with_digits(self) -> None:
        validate_project_name("server2")

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_project_name("")

    def test_starts_with_digit_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("123server")

    def test_starts_with_hyphen_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("-server")

    def test_special_chars_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("my server!")

    def test_dots_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("my.server")

    def test_slashes_rejected(self) -> None:
        with pytest.raises(ValueError, match="Invalid project name"):
            validate_project_name("my/server")

    def test_single_letter(self) -> None:
        validate_project_name("s")  # minimal valid name


# -- Tool name validation -----------------------------------------------------


class TestValidateToolNames:
    def test_valid_names(self) -> None:
        validate_tool_names(["weather", "calculator", "search2"])

    def test_empty_tool_name_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_tool_names(["weather", ""])

    def test_hyphenated_tool_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid tool name"):
            validate_tool_names(["my-tool"])

    def test_tool_starting_with_digit_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid tool name"):
            validate_tool_names(["2fast"])

    def test_empty_list_ok(self) -> None:
        validate_tool_names([])  # no tools to validate


# -- Scaffold with invalid inputs ---------------------------------------------


class TestScaffoldValidation:
    def test_scaffold_empty_name_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            scaffold_project("", output_dir=tmp_path)

    def test_scaffold_bad_name_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid project name"):
            scaffold_project("123bad", output_dir=tmp_path)

    def test_scaffold_bad_tool_name_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid tool name"):
            scaffold_project("good-name", output_dir=tmp_path, tools=["bad-tool"])

    def test_scaffold_valid_name_succeeds(self, tmp_path: Path) -> None:
        project = scaffold_project("valid-name", output_dir=tmp_path)
        assert project.exists()


# -- CLI error handling for invalid names --------------------------------------


class TestCLINewValidation:
    def test_invalid_name_exits_with_error(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "123bad", "-o", str(tmp_path)])
        assert result.exit_code == 1
        assert "Invalid project name" in result.output

    def test_invalid_tool_name_exits_with_error(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "good-server", "-t", "bad-tool", "-o", str(tmp_path)])
        assert result.exit_code == 1
        assert "Invalid tool name" in result.output

    def test_empty_tool_list_still_works(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "no-tools", "-t", "", "-o", str(tmp_path)])
        assert result.exit_code == 0


# -- Resource definition validation -------------------------------------------


class TestValidateResourceDefinitions:
    def test_valid_resource(self) -> None:
        resources = [
            {"uri": "file://data", "name": "Data file"},
        ]
        report = validate_resource_definitions(resources)
        assert report.is_valid

    def test_multiple_valid_resources(self) -> None:
        resources = [
            {"uri": "file://data", "name": "Data"},
            {"uri": "http://api", "name": "API"},
        ]
        report = validate_resource_definitions(resources)
        assert report.is_valid

    def test_empty_list_is_valid(self) -> None:
        report = validate_resource_definitions([])
        assert report.is_valid

    def test_missing_uri(self) -> None:
        resources = [{"name": "Missing URI"}]
        report = validate_resource_definitions(resources)
        assert not report.is_valid

    def test_missing_name(self) -> None:
        resources = [{"uri": "file://test"}]
        report = validate_resource_definitions(resources)
        assert not report.is_valid

    def test_empty_uri_invalid(self) -> None:
        resources = [{"uri": "", "name": "Bad"}]
        report = validate_resource_definitions(resources)
        assert not report.is_valid

    def test_duplicate_uris(self) -> None:
        resources = [
            {"uri": "file://data", "name": "First"},
            {"uri": "file://data", "name": "Second"},
        ]
        report = validate_resource_definitions(resources)
        assert not report.is_valid
        dup_errors = [e for e in report.errors if "Duplicate" in e.message]
        assert len(dup_errors) == 1

    def test_with_optional_fields(self) -> None:
        resources = [
            {
                "uri": "file://docs",
                "name": "Docs",
                "description": "Documentation files",
                "mimeType": "text/plain",
            },
        ]
        report = validate_resource_definitions(resources)
        assert report.is_valid


# -- Tool definitions: more edge cases ----------------------------------------


class TestToolDefinitionEdgeCases:
    def test_wrong_input_schema_type(self) -> None:
        """inputSchema.type must be 'object', not 'string'."""
        tools = [
            {
                "name": "bad",
                "description": "Bad schema type",
                "inputSchema": {"type": "string"},
            }
        ]
        report = validate_tool_definitions(tools)
        assert not report.is_valid

    def test_none_name_in_tool(self) -> None:
        """Tool with None as name should fail validation."""
        tools = [
            {
                "name": None,
                "description": "Null name",
                "inputSchema": {"type": "object"},
            }
        ]
        report = validate_tool_definitions(tools)
        assert not report.is_valid


# -- Snake/title case edge cases -----------------------------------------------


class TestCaseConversionEdgeCases:
    def test_snake_case_empty(self) -> None:
        assert snake_case("") == ""

    def test_title_case_empty(self) -> None:
        assert title_case("") == ""

    def test_snake_case_numbers(self) -> None:
        assert snake_case("server-2-go") == "server_2_go"

    def test_title_case_numbers(self) -> None:
        assert title_case("my-2nd-server") == "My 2Nd Server"

    def test_snake_case_consecutive_hyphens(self) -> None:
        # Double hyphens become double underscores
        assert snake_case("my--server") == "my__server"
