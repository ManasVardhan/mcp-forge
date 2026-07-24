"""Tests for MCP prompts scaffolding support.

Covers prompt name validation, generated prompts.py content, server
wiring, the CLI --prompts option, inspect prompt display, and running
the generated test suite of a project scaffolded with prompts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from mcp_forge.cli import cli
from mcp_forge.scaffold import scaffold_project, validate_prompt_names


@pytest.fixture
def runner():
    return CliRunner()


# -----------------------------------------------------------------------
# validate_prompt_names
# -----------------------------------------------------------------------

class TestValidatePromptNames:
    def test_valid_names_pass(self):
        validate_prompt_names(["summarize", "code_review", "q1"])

    def test_empty_name_rejected(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_prompt_names([""])

    def test_hyphen_rejected(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_names(["bad-prompt"])

    def test_leading_digit_rejected(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_names(["1prompt"])

    def test_spaces_rejected(self):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            validate_prompt_names(["my prompt"])


# -----------------------------------------------------------------------
# scaffold_project with prompts
# -----------------------------------------------------------------------

class TestScaffoldPrompts:
    def test_prompts_file_generated(self, tmp_path: Path):
        project = scaffold_project(
            "my-server", output_dir=tmp_path, prompts=["summarize", "code_review"]
        )
        content = (project / "src" / "my_server" / "prompts.py").read_text()
        assert '"name": "summarize"' in content
        assert '"name": "code_review"' in content
        assert "async def _prompt_summarize" in content
        assert "async def _prompt_code_review" in content
        assert "handle_get_prompt" in content

    def test_prompts_file_written_even_without_prompts(self, tmp_path: Path):
        project = scaffold_project("my-server", output_dir=tmp_path)
        prompts_py = project / "src" / "my_server" / "prompts.py"
        assert prompts_py.exists()
        assert "PROMPTS" in prompts_py.read_text()

    def test_server_wires_prompts_when_present(self, tmp_path: Path):
        project = scaffold_project(
            "my-server", output_dir=tmp_path, prompts=["summarize"]
        )
        server = (project / "src" / "my_server" / "server.py").read_text()
        assert "from .prompts import PROMPTS, handle_get_prompt" in server
        assert '"prompts/list"' in server
        assert '"prompts/get"' in server
        assert '"prompts": {"listChanged": False}' in server

    def test_server_omits_prompts_when_absent(self, tmp_path: Path):
        project = scaffold_project("my-server", output_dir=tmp_path)
        server = (project / "src" / "my_server" / "server.py").read_text()
        assert "from .prompts" not in server
        assert "prompts/list" not in server

    def test_invalid_prompt_name_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            scaffold_project("my-server", output_dir=tmp_path, prompts=["bad-name"])

    def test_readme_lists_prompts(self, tmp_path: Path):
        project = scaffold_project(
            "my-server", output_dir=tmp_path, prompts=["summarize"]
        )
        readme = (project / "README.md").read_text()
        assert "## Prompts" in readme
        assert "summarize" in readme

    def test_generated_prompts_file_compiles(self, tmp_path: Path):
        project = scaffold_project(
            "my-server", output_dir=tmp_path, prompts=["alpha", "beta"]
        )
        content = (project / "src" / "my_server" / "prompts.py").read_text()
        compile(content, "prompts.py", "exec")

    def test_generated_tests_cover_prompts(self, tmp_path: Path):
        project = scaffold_project(
            "my-server", output_dir=tmp_path, prompts=["summarize"]
        )
        tests = (project / "tests" / "test_my_server.py").read_text()
        assert "def test_prompts_list_contains_scaffolded_prompts" in tests
        assert "def test_prompt_summarize_get" in tests
        assert "def test_unknown_prompt_returns_error" in tests
        assert "def test_initialize_declares_prompts_capability" in tests

    def test_no_prompt_tests_without_prompts(self, tmp_path: Path):
        project = scaffold_project("my-server", output_dir=tmp_path)
        tests = (project / "tests" / "test_my_server.py").read_text()
        assert "test_prompts_list" not in tests
        assert "test_unknown_prompt_returns_error" not in tests


# -----------------------------------------------------------------------
# Generated server behavior (direct dispatch through the rendered code)
# -----------------------------------------------------------------------

class TestGeneratedServerPrompts:
    def _load_server(self, project: Path, pkg: str):
        import asyncio
        import importlib

        sys.path.insert(0, str(project / "src"))
        try:
            for mod in [pkg, f"{pkg}.server", f"{pkg}.tools", f"{pkg}.prompts"]:
                sys.modules.pop(mod, None)
            server_mod = importlib.import_module(f"{pkg}.server")
            server = server_mod.MCPServer()

            def rpc(method: str, params: dict | None = None) -> dict:
                request = {"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params or {}}
                return asyncio.run(server.handle_request(request))

            return rpc
        finally:
            sys.path.remove(str(project / "src"))

    def test_prompts_list_and_get(self, tmp_path: Path):
        project = scaffold_project(
            "prompt-server", output_dir=tmp_path, prompts=["summarize"]
        )
        rpc = self._load_server(project, "prompt_server")

        listed = rpc("prompts/list")
        names = [p["name"] for p in listed["result"]["prompts"]]
        assert names == ["summarize"]

        got = rpc("prompts/get", {"name": "summarize",
                                  "arguments": {"topic": "testing"}})
        messages = got["result"]["messages"]
        assert messages[0]["role"] == "user"
        assert "testing" in messages[0]["content"]["text"]

    def test_prompts_get_without_topic(self, tmp_path: Path):
        project = scaffold_project(
            "topicless-server", output_dir=tmp_path, prompts=["draft_email"]
        )
        rpc = self._load_server(project, "topicless_server")
        got = rpc("prompts/get", {"name": "draft_email", "arguments": {}})
        text = got["result"]["messages"][0]["content"]["text"]
        assert "Draft Email" in text
        assert "about" not in text

    def test_unknown_prompt_errors(self, tmp_path: Path):
        project = scaffold_project(
            "err-server", output_dir=tmp_path, prompts=["summarize"]
        )
        rpc = self._load_server(project, "err_server")
        resp = rpc("prompts/get", {"name": "nope", "arguments": {}})
        assert "error" in resp
        assert "nope" in resp["error"]["message"]

    def test_initialize_declares_prompts(self, tmp_path: Path):
        project = scaffold_project(
            "cap-server", output_dir=tmp_path, prompts=["summarize"]
        )
        rpc = self._load_server(project, "cap_server")
        resp = rpc("initialize")
        assert resp["result"]["capabilities"]["prompts"] == {"listChanged": False}


# -----------------------------------------------------------------------
# CLI new --prompts
# -----------------------------------------------------------------------

class TestCliNewPrompts:
    def test_new_with_prompts_flag(self, runner, tmp_path: Path):
        result = runner.invoke(cli, [
            "new", "cli-server", "-o", str(tmp_path),
            "--prompts", "summarize,code_review",
        ])
        assert result.exit_code == 0
        prompts_py = tmp_path / "cli-server" / "src" / "cli_server" / "prompts.py"
        assert '"name": "summarize"' in prompts_py.read_text()

    def test_new_with_short_flag_and_spaces(self, runner, tmp_path: Path):
        result = runner.invoke(cli, [
            "new", "short-server", "-o", str(tmp_path), "-p", " summarize , qa ",
        ])
        assert result.exit_code == 0
        content = (tmp_path / "short-server" / "src" / "short_server"
                   / "prompts.py").read_text()
        assert '"name": "summarize"' in content
        assert '"name": "qa"' in content

    def test_new_invalid_prompt_name_exits_1(self, runner, tmp_path: Path):
        result = runner.invoke(cli, [
            "new", "bad-server", "-o", str(tmp_path), "-p", "bad-prompt",
        ])
        assert result.exit_code == 1
        assert "Invalid prompt name" in result.output

    def test_new_help_mentions_prompts(self, runner):
        result = runner.invoke(cli, ["new", "--help"])
        assert result.exit_code == 0
        assert "--prompts" in result.output


# -----------------------------------------------------------------------
# inspect shows prompts
# -----------------------------------------------------------------------

class TestInspectPrompts:
    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_rich_output_with_prompts(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.send_request.side_effect = [
            {"result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "prompt-server", "version": "1.0"},
                "capabilities": {"tools": {}, "prompts": {}},
            }},
            {"result": {"tools": []}},
            {"result": {"resources": []}},
            {"result": {"prompts": [
                {"name": "summarize", "description": "Summarize prompt",
                 "arguments": [{"name": "topic", "required": False}]},
            ]}},
        ]

        result = runner.invoke(cli, ["inspect", "--cmd", "python s.py"])
        assert result.exit_code == 0
        assert "Prompts (1)" in result.output
        assert "summarize" in result.output
        assert "topic" in result.output

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_json_output_includes_prompts(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.send_request.side_effect = [
            {"result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "prompt-server", "version": "1.0"},
                "capabilities": {},
            }},
            {"result": {"tools": []}},
            {"result": {"resources": []}},
            {"result": {"prompts": [{"name": "summarize", "arguments": []}]}},
        ]

        result = runner.invoke(cli, ["inspect", "--cmd", "python s.py",
                                     "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["prompts"][0]["name"] == "summarize"

    @patch("mcp_forge.cli.MCPTestClient")
    def test_inspect_tolerates_missing_prompt_support(self, mock_cls, runner):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.send_request.side_effect = [
            {"result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "old-server", "version": "1.0"},
                "capabilities": {"tools": {}},
            }},
            {"result": {"tools": []}},
            {"result": {"resources": []}},
            {"error": {"code": -32603, "message": "Unknown method: prompts/list"}},
        ]

        result = runner.invoke(cli, ["inspect", "--cmd", "python s.py",
                                     "--json-output"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["prompts"] == []


# -----------------------------------------------------------------------
# Generated suite runs end to end with prompts
# -----------------------------------------------------------------------

class TestGeneratedSuiteWithPrompts:
    def test_generated_suite_passes_with_prompts(self, tmp_path: Path):
        project = scaffold_project(
            "full-server",
            output_dir=tmp_path,
            tools=["lookup"],
            resources=["notes://all"],
            prompts=["summarize", "code_review"],
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project / "src")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "18 passed" in result.stdout
