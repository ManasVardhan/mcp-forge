"""Tests for the inspect and info CLI commands, and __main__.py module support."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mcp_forge.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def scaffold_project(tmp_path):
    """Create a minimal scaffolded project for info command tests."""
    from mcp_forge.scaffold import scaffold_project as do_scaffold
    return do_scaffold("test-server", output_dir=tmp_path)


# -----------------------------------------------------------------------
# inspect command tests
# -----------------------------------------------------------------------

class TestInspect:
    """Tests for mcp-forge inspect command."""

    def test_inspect_help(self, runner):
        result = runner.invoke(cli, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "Inspect" in result.output or "inspect" in result.output
        assert "--cmd" in result.output

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_rich_output(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.send_request.side_effect = [
            # initialize
            {"result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "test-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }},
            # tools/list
            {"result": {"tools": [
                {"name": "greet", "description": "Say hello", "inputSchema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }},
            ]}},
            # resources/list
            {"result": {"resources": [
                {"uri": "file://data.txt", "name": "data", "mimeType": "text/plain"},
            ]}},
        ]

        result = runner.invoke(cli, ["inspect", "--cmd", "python server.py"])
        assert result.exit_code == 0
        assert "test-server" in result.output
        assert "greet" in result.output
        assert "file://data.txt" in result.output
        mock_client.start.assert_called_once()
        mock_client.stop.assert_called_once()

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_json_output(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.send_request.side_effect = [
            {"result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "json-server", "version": "0.1.0"},
                "capabilities": {},
            }},
            {"result": {"tools": []}},
            {"result": {"resources": []}},
        ]

        result = runner.invoke(cli, ["inspect", "--cmd", "python s.py", "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["serverInfo"]["name"] == "json-server"
        assert data["protocolVersion"] == "2024-11-05"
        assert data["tools"] == []
        assert data["resources"] == []

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_no_tools_no_resources(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.send_request.side_effect = [
            {"result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "empty-server", "version": "0.0.1"},
                "capabilities": {},
            }},
            {"result": {"tools": []}},
            {"result": {"resources": []}},
        ]

        result = runner.invoke(cli, ["inspect", "--cmd", "python s.py"])
        assert result.exit_code == 0
        assert "No tools registered" in result.output

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_start_failure(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.start.side_effect = OSError("Cannot start process")

        result = runner.invoke(cli, ["inspect", "--cmd", "bad-command"])
        assert result.exit_code != 0
        assert "Failed to start server" in result.output

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_communication_error(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.send_request.side_effect = RuntimeError("No response")

        result = runner.invoke(cli, ["inspect", "--cmd", "python s.py"])
        assert result.exit_code != 0
        assert "Error communicating" in result.output
        mock_client.stop.assert_called_once()

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_multiple_tools(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        tools = [
            {"name": f"tool_{i}", "description": f"Tool {i}",
             "inputSchema": {"type": "object", "properties": {}}}
            for i in range(5)
        ]

        mock_client.send_request.side_effect = [
            {"result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "multi", "version": "1.0"},
                "capabilities": {"tools": {}, "resources": {}},
            }},
            {"result": {"tools": tools}},
            {"result": {"resources": []}},
        ]

        result = runner.invoke(cli, ["inspect", "--cmd", "python s.py"])
        assert result.exit_code == 0
        assert "tool_0" in result.output
        assert "tool_4" in result.output
        assert "Tools (5)" in result.output

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_with_cwd(self, mock_cls, runner, tmp_path):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        mock_client.send_request.side_effect = [
            {"result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "cwd-server", "version": "1.0"},
                "capabilities": {},
            }},
            {"result": {"tools": []}},
            {"result": {"resources": []}},
        ]

        result = runner.invoke(cli, ["inspect", "--cmd", "python s.py", "--cwd", str(tmp_path)])
        assert result.exit_code == 0
        # Verify cwd was passed
        mock_cls.assert_called_once()
        call_args = mock_cls.call_args
        assert call_args[1]["cwd"] == tmp_path


# -----------------------------------------------------------------------
# info command tests
# -----------------------------------------------------------------------

class TestInfo:
    """Tests for mcp-forge info command."""

    def test_info_help(self, runner):
        result = runner.invoke(cli, ["info", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output

    def test_info_text_output(self, runner, scaffold_project):
        result = runner.invoke(cli, ["info", str(scaffold_project)])
        assert result.exit_code == 0
        assert "test-server" in result.output
        assert "Source Files" in result.output
        assert "Valid Structure" in result.output or "Yes" in result.output

    def test_info_json_output(self, runner, scaffold_project):
        result = runner.invoke(cli, ["info", str(scaffold_project), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "test-server"
        assert data["valid_structure"] is True
        assert data["source_files"] > 0
        assert data["total_lines"] > 0
        assert data["has_tests"] is True

    def test_info_markdown_output(self, runner, scaffold_project):
        result = runner.invoke(cli, ["info", str(scaffold_project), "--format", "markdown"])
        assert result.exit_code == 0
        assert "# test-server" in result.output
        assert "Source files:" in result.output
        assert "Valid structure: Yes" in result.output

    def test_info_no_pyproject(self, runner, tmp_path):
        result = runner.invoke(cli, ["info", str(tmp_path)])
        assert result.exit_code != 0
        assert "No pyproject.toml" in result.output

    def test_info_has_dockerfile(self, runner, scaffold_project):
        result = runner.invoke(cli, ["info", str(scaffold_project), "--format", "json"])
        data = json.loads(result.output)
        assert data["has_dockerfile"] is True

    def test_info_has_readme(self, runner, scaffold_project):
        result = runner.invoke(cli, ["info", str(scaffold_project), "--format", "json"])
        data = json.loads(result.output)
        assert data["has_readme"] is True

    def test_info_no_ci(self, runner, scaffold_project):
        result = runner.invoke(cli, ["info", str(scaffold_project), "--format", "json"])
        data = json.loads(result.output)
        # Scaffolded projects don't have .github/workflows
        assert data["has_ci"] is False

    def test_info_with_ci(self, runner, scaffold_project):
        ci_dir = scaffold_project / ".github" / "workflows"
        ci_dir.mkdir(parents=True)
        result = runner.invoke(cli, ["info", str(scaffold_project), "--format", "json"])
        data = json.loads(result.output)
        assert data["has_ci"] is True


# -----------------------------------------------------------------------
# __main__.py tests
# -----------------------------------------------------------------------

class TestMainModule:
    """Tests for python -m mcp_forge support."""

    def test_main_module_imports(self):
        import mcp_forge.__main__  # noqa: F401

    def test_main_module_version_subprocess(self):
        result = subprocess.run(
            [sys.executable, "-m", "mcp_forge", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "mcp-forge" in result.stdout

    def test_main_module_help_subprocess(self):
        result = subprocess.run(
            [sys.executable, "-m", "mcp_forge", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "MCP Forge" in result.stdout

    def test_main_module_inspect_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "mcp_forge", "inspect", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--cmd" in result.stdout

    def test_main_module_info_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "mcp_forge", "info", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--format" in result.stdout
