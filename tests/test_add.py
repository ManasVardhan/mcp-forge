"""Tests for the add command and augment module."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from mcp_forge.augment import (
    AugmentError,
    add_tools,
    existing_tool_names,
    find_package_dir,
)
from mcp_forge.cli import cli
from mcp_forge.scaffold import scaffold_project


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return scaffold_project("demo-server", output_dir=tmp_path, tools=["weather"])


def _tools_source(project: Path) -> str:
    return (project / "src" / "demo_server" / "tools.py").read_text()


def _tests_source(project: Path) -> str:
    return (project / "tests" / "test_demo_server.py").read_text()


def test_find_package_dir(project: Path):
    assert find_package_dir(project).name == "demo_server"


def test_find_package_dir_rejects_non_project(tmp_path: Path):
    with pytest.raises(AugmentError, match="No src/"):
        find_package_dir(tmp_path)


def test_find_package_dir_rejects_missing_tools(tmp_path: Path):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    with pytest.raises(AugmentError, match="tools.py"):
        find_package_dir(tmp_path)


def test_existing_tool_names(project: Path):
    assert existing_tool_names(_tools_source(project)) == ["weather"]


def test_add_tools_updates_registry_dispatch_and_handler(project: Path):
    report = add_tools(project, ["forecast"])
    source = _tools_source(project)
    assert '"name": "forecast"' in source
    assert 'if name == "forecast":' in source
    assert "async def _tool_forecast(" in source
    assert report.added == ["forecast"]
    assert report.package == "demo_server"


def test_add_tools_result_is_valid_python(project: Path):
    add_tools(project, ["forecast", "alerts"])
    ast.parse(_tools_source(project))
    ast.parse(_tests_source(project))


def test_add_tools_preserves_existing_tool(project: Path):
    add_tools(project, ["forecast"])
    source = _tools_source(project)
    assert existing_tool_names(source) == ["weather", "forecast"]


def test_add_tools_updates_generated_tests(project: Path):
    add_tools(project, ["forecast"])
    tests = _tests_source(project)
    assert '"weather", "forecast"' in tests
    assert "def test_tool_forecast_call()" in tests


def test_add_tools_rejects_duplicate_existing(project: Path):
    with pytest.raises(AugmentError, match="already defined"):
        add_tools(project, ["weather"])


def test_add_tools_rejects_duplicate_request(project: Path):
    with pytest.raises(AugmentError, match="Duplicate"):
        add_tools(project, ["forecast", "forecast"])


def test_add_tools_rejects_invalid_name(project: Path):
    with pytest.raises(AugmentError, match="Invalid tool name"):
        add_tools(project, ["bad-name"])


def test_add_tools_rejects_mangled_registry(project: Path):
    tools_path = project / "src" / "demo_server" / "tools.py"
    tools_path.write_text("something completely different\n")
    with pytest.raises(AugmentError, match="registry"):
        add_tools(project, ["forecast"])


def test_add_tools_missing_test_file_is_noted(project: Path):
    (project / "tests" / "test_demo_server.py").unlink()
    report = add_tools(project, ["forecast"])
    assert any("tests not updated" in note for note in report.notes)
    assert len(report.changed_files) == 1


def test_added_tool_dispatches(project: Path):
    """The generated server actually serves the new tool end to end."""
    add_tools(project, ["forecast"])
    code = (
        "import asyncio, json, sys\n"
        "sys.path.insert(0, 'src')\n"
        "from demo_server.server import MCPServer\n"
        "server = MCPServer()\n"
        "req = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',\n"
        "       'params': {'name': 'forecast', 'arguments': {'query': 'LA'}}}\n"
        "resp = asyncio.run(server.handle_request(req))\n"
        "print(json.dumps(resp))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=project, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert "forecast result for: LA" in proc.stdout


def test_cli_add_tool(project: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli, ["add", "tool", "forecast", "--project-dir", str(project)]
    )
    assert result.exit_code == 0
    assert "forecast" in result.output
    assert "async def _tool_forecast(" in _tools_source(project)


def test_cli_add_tool_duplicate_fails(project: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli, ["add", "tool", "weather", "--project-dir", str(project)]
    )
    assert result.exit_code == 1
    assert "already defined" in result.output


def test_cli_add_tool_multiple(project: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli, ["add", "tool", "forecast", "alerts", "--project-dir", str(project)]
    )
    assert result.exit_code == 0
    assert existing_tool_names(_tools_source(project)) == [
        "weather",
        "forecast",
        "alerts",
    ]
