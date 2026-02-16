"""Tests for the validator module."""

from pathlib import Path

from mcp_forge.validator import (
    validate_initialize_response,
    validate_project_structure,
    validate_tool_definitions,
    validate_tool_result,
)


def test_validate_valid_tool():
    tools = [
        {
            "name": "weather",
            "description": "Get weather",
            "inputSchema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]
    report = validate_tool_definitions(tools)
    assert report.is_valid


def test_validate_tool_missing_name():
    tools = [{"description": "No name", "inputSchema": {"type": "object"}}]
    report = validate_tool_definitions(tools)
    assert not report.is_valid


def test_validate_duplicate_tool_names():
    tools = [
        {"name": "x", "description": "A", "inputSchema": {"type": "object"}},
        {"name": "x", "description": "B", "inputSchema": {"type": "object"}},
    ]
    report = validate_tool_definitions(tools)
    assert not report.is_valid


def test_validate_empty_tools():
    report = validate_tool_definitions([])
    assert report.is_valid  # just a warning
    assert len(report.warnings) == 1


def test_validate_initialize_response_valid():
    resp = {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "serverInfo": {"name": "test", "version": "1.0"},
    }
    report = validate_initialize_response(resp)
    assert report.is_valid


def test_validate_initialize_response_invalid():
    report = validate_initialize_response({"protocolVersion": "1.0"})
    assert not report.is_valid


def test_validate_tool_result_valid():
    result = {"content": [{"type": "text", "text": "hello"}]}
    report = validate_tool_result(result)
    assert report.is_valid


def test_validate_tool_result_invalid():
    report = validate_tool_result({"not_content": []})
    assert not report.is_valid


def test_validate_project_structure(tmp_path: Path):
    # Empty dir should fail
    report = validate_project_structure(tmp_path)
    assert not report.is_valid
