"""Tests for live protocol validation (validate_live_server and validate --cmd)."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from click.testing import CliRunner

from mcp_forge.cli import cli
from mcp_forge.validator import validate_live_server, validate_prompt_definitions

FAKE_SERVER_TEMPLATE = """\
import json
import sys

INIT_RESULT = {init_result}
TOOLS_RESULT = {tools_result}
RESOURCES_RESULT = {resources_result}
PROMPTS_RESULT = {prompts_result}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    if "id" not in req:
        continue  # notification
    method = req["method"]
    if method == "initialize":
        payload = INIT_RESULT
    elif method == "tools/list":
        payload = TOOLS_RESULT
    elif method == "resources/list":
        payload = RESOURCES_RESULT
    elif method == "prompts/list":
        payload = PROMPTS_RESULT
    else:
        payload = {{"__error__": {{"code": -32601, "message": "Method not found"}}}}
    resp = {{"jsonrpc": "2.0", "id": req["id"]}}
    if isinstance(payload, dict) and "__error__" in payload:
        resp["error"] = payload["__error__"]
    else:
        resp["result"] = payload
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
"""

GOOD_INIT = {
    "protocolVersion": "2024-11-05",
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "fake-server", "version": "0.1.0"},
}

GOOD_TOOLS = {
    "tools": [
        {
            "name": "echo",
            "description": "Echo text back",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        }
    ]
}

ERROR_PAYLOAD = {"__error__": {"code": -32601, "message": "Method not found"}}


def _write_fake_server(
    tmp_path: Path,
    init_result=GOOD_INIT,
    tools_result=GOOD_TOOLS,
    resources_result=ERROR_PAYLOAD,
    prompts_result=ERROR_PAYLOAD,
) -> list[str]:
    """Write a fake MCP server script and return the command to run it."""
    script = tmp_path / "fake_server.py"
    script.write_text(
        FAKE_SERVER_TEMPLATE.format(
            init_result=repr(init_result),
            tools_result=repr(tools_result),
            resources_result=repr(resources_result),
            prompts_result=repr(prompts_result),
        )
    )
    return [sys.executable, str(script)]


class TestValidateLiveServerHappyPath:
    def test_compliant_server_passes(self, tmp_path: Path) -> None:
        cmd = _write_fake_server(tmp_path)
        report = validate_live_server(cmd)
        assert report.is_valid
        assert report.errors == []

    def test_server_with_resources_and_prompts(self, tmp_path: Path) -> None:
        init = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            "serverInfo": {"name": "full", "version": "1.0"},
        }
        resources = {"resources": [{"uri": "file://data", "name": "data"}]}
        prompts = {"prompts": [{"name": "summarize", "arguments": [{"name": "text"}]}]}
        cmd = _write_fake_server(
            tmp_path, init_result=init, resources_result=resources, prompts_result=prompts
        )
        report = validate_live_server(cmd)
        assert report.is_valid


class TestValidateLiveServerFailures:
    def test_server_fails_to_start(self) -> None:
        report = validate_live_server(["nonexistent_command_98765"])
        assert not report.is_valid
        assert report.errors[0].category == "startup"

    def test_bad_initialize_response(self, tmp_path: Path) -> None:
        bad_init = {"protocolVersion": "2024-11-05"}  # missing capabilities, serverInfo
        cmd = _write_fake_server(tmp_path, init_result=bad_init)
        report = validate_live_server(cmd)
        assert not report.is_valid
        assert any(i.category == "initialize" for i in report.errors)

    def test_initialize_error_response(self, tmp_path: Path) -> None:
        cmd = _write_fake_server(tmp_path, init_result=ERROR_PAYLOAD)
        report = validate_live_server(cmd)
        assert not report.is_valid
        assert any(i.category == "initialize" for i in report.errors)

    def test_invalid_tool_definition(self, tmp_path: Path) -> None:
        bad_tools = {"tools": [{"name": "broken"}]}  # missing description, inputSchema
        cmd = _write_fake_server(tmp_path, tools_result=bad_tools)
        report = validate_live_server(cmd)
        assert not report.is_valid
        assert any(i.category == "tools" for i in report.errors)

    def test_duplicate_tool_names(self, tmp_path: Path) -> None:
        tool = GOOD_TOOLS["tools"][0]
        cmd = _write_fake_server(tmp_path, tools_result={"tools": [tool, tool]})
        report = validate_live_server(cmd)
        assert not report.is_valid
        assert any("Duplicate" in i.message for i in report.errors)

    def test_declared_tools_capability_but_list_errors(self, tmp_path: Path) -> None:
        cmd = _write_fake_server(tmp_path, tools_result=ERROR_PAYLOAD)
        report = validate_live_server(cmd)
        assert not report.is_valid
        assert any("tools/list returned an error" in i.message for i in report.errors)

    def test_declared_resources_capability_but_list_errors(self, tmp_path: Path) -> None:
        init = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "s", "version": "1"},
        }
        cmd = _write_fake_server(tmp_path, init_result=init)
        report = validate_live_server(cmd)
        assert not report.is_valid
        assert any("resources/list" in i.message for i in report.errors)


class TestValidateLiveServerWarnings:
    def test_undeclared_tools_capability_warns(self, tmp_path: Path) -> None:
        init = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "s", "version": "1"},
        }
        cmd = _write_fake_server(tmp_path, init_result=init)
        report = validate_live_server(cmd)
        assert report.is_valid  # warnings only
        assert any("does not declare the tools capability" in i.message for i in report.warnings)

    def test_undeclared_prompts_capability_warns(self, tmp_path: Path) -> None:
        init = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "s", "version": "1"},
        }
        prompts = {"prompts": [{"name": "summarize"}]}
        cmd = _write_fake_server(tmp_path, init_result=init, prompts_result=prompts)
        report = validate_live_server(cmd)
        assert report.is_valid
        assert any("prompts capability" in i.message for i in report.warnings)


class TestValidatePromptDefinitions:
    def test_empty_list_is_valid(self) -> None:
        assert validate_prompt_definitions([]).is_valid

    def test_valid_prompts(self) -> None:
        prompts = [
            {"name": "a", "description": "d", "arguments": [{"name": "x", "required": True}]},
            {"name": "b"},
        ]
        assert validate_prompt_definitions(prompts).is_valid

    def test_missing_name_is_error(self) -> None:
        report = validate_prompt_definitions([{"description": "no name"}])
        assert not report.is_valid

    def test_duplicate_names_are_errors(self) -> None:
        report = validate_prompt_definitions([{"name": "a"}, {"name": "a"}])
        assert not report.is_valid
        assert any("Duplicate" in i.message for i in report.errors)

    def test_bad_argument_shape_is_error(self) -> None:
        report = validate_prompt_definitions([{"name": "a", "arguments": [{"required": True}]}])
        assert not report.is_valid


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal valid project structure."""
    project = tmp_path / "proj"
    pkg = project / "src" / "proj"
    pkg.mkdir(parents=True)
    (project / "pyproject.toml").write_text('[project]\nname = "proj"\n')
    (pkg / "__init__.py").write_text("")
    (pkg / "server.py").write_text("")
    (pkg / "tools.py").write_text("")
    (project / "README.md").write_text("# proj")
    (project / "Dockerfile").write_text("FROM python:3.12")
    (project / ".gitignore").write_text("*.pyc")
    return project


class TestValidateCLILive:
    def test_validate_with_cmd_passes(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        cmd = _write_fake_server(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(project), "--cmd", " ".join(cmd)])
        assert result.exit_code == 0
        assert "Live protocol is valid" in result.output

    def test_validate_with_cmd_fails_on_bad_server(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        cmd = _write_fake_server(tmp_path, tools_result={"tools": [{"name": "broken"}]})
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(project), "--cmd", " ".join(cmd)])
        assert result.exit_code == 1

    def test_validate_json_output(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        cmd = _write_fake_server(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["validate", str(project), "--cmd", " ".join(cmd), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["valid"] is True
        assert data["structure"]["valid"] is True
        assert data["live"]["valid"] is True

    def test_validate_json_without_cmd(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(project), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["live"] is None
        assert data["valid"] is True

    def test_validate_json_failure_exit_code(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        cmd = _write_fake_server(tmp_path, init_result={"protocolVersion": "x"})
        runner = CliRunner()
        result = runner.invoke(
            cli, ["validate", str(project), "--cmd", " ".join(cmd), "--json"]
        )
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["valid"] is False
        assert data["live"]["valid"] is False

    def test_validate_structure_only_still_works(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(project)])
        assert result.exit_code == 0
        assert "Project structure is valid" in result.output


class TestValidateCLIScaffoldedServer:
    """End-to-end: a scaffolded project passes live validation."""

    def test_scaffolded_server_passes_live_validation(self, tmp_path: Path) -> None:
        from mcp_forge.scaffold import scaffold_project

        project = scaffold_project(
            "live-server",
            output_dir=tmp_path,
            tools=["echo"],
            prompts=["summarize"],
        )
        script = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(project / "src")!r})
            from live_server.server import main
            main()
            """
        )
        runner_script = tmp_path / "run_live_server.py"
        runner_script.write_text(script)
        report = validate_live_server([sys.executable, str(runner_script)])
        assert report.errors == []
        assert report.is_valid
