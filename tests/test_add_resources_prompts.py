"""Tests for adding resources and prompts to existing projects."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from mcp_forge.augment import (
    AugmentError,
    add_prompts,
    add_resources,
    existing_prompt_names,
    existing_resource_uris,
    validate_resource_uris,
)
from mcp_forge.cli import cli
from mcp_forge.scaffold import scaffold_project


@pytest.fixture()
def bare_project(tmp_path: Path) -> Path:
    """A project scaffolded with tools only (no resources, no prompts)."""
    return scaffold_project("demo-server", output_dir=tmp_path, tools=["weather"])


@pytest.fixture()
def full_project(tmp_path: Path) -> Path:
    """A project scaffolded with resources and prompts already wired."""
    return scaffold_project(
        "demo-server",
        output_dir=tmp_path,
        tools=["weather"],
        resources=["docs://readme"],
        prompts=["summarize"],
    )


def _pkg(project: Path) -> Path:
    return project / "src" / "demo_server"


def _tests_source(project: Path) -> str:
    return (project / "tests" / "test_demo_server.py").read_text()


def _rpc_via_subprocess(project: Path, method: str, params: dict) -> dict:
    code = (
        "import asyncio, json, sys\n"
        "sys.path.insert(0, 'src')\n"
        "from demo_server.server import MCPServer\n"
        "server = MCPServer()\n"
        f"req = {{'jsonrpc': '2.0', 'id': 1, 'method': {method!r}, 'params': {params!r}}}\n"
        "resp = asyncio.run(server.handle_request(req))\n"
        "print(json.dumps(resp))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=project, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------


class TestValidation:
    def test_valid_uris_pass(self) -> None:
        validate_resource_uris(["docs://readme", "file://a/b.txt", "app+x://thing"])

    def test_empty_uri_rejected(self) -> None:
        with pytest.raises(AugmentError, match="cannot be empty"):
            validate_resource_uris([""])

    def test_missing_scheme_rejected(self) -> None:
        with pytest.raises(AugmentError, match="Invalid resource URI"):
            validate_resource_uris(["readme"])

    def test_quote_in_uri_rejected(self) -> None:
        with pytest.raises(AugmentError, match="Invalid resource URI"):
            validate_resource_uris(['docs://a"b'])

    def test_space_in_uri_rejected(self) -> None:
        with pytest.raises(AugmentError, match="Invalid resource URI"):
            validate_resource_uris(["docs://a b"])


# ---------------------------------------------------------------------------
# add_resources
# ---------------------------------------------------------------------------


class TestAddResources:
    def test_updates_registry(self, full_project: Path) -> None:
        report = add_resources(full_project, ["docs://guide"])
        source = (_pkg(full_project) / "resources.py").read_text()
        assert existing_resource_uris(source) == ["docs://readme", "docs://guide"]
        assert report.added == ["docs://guide"]

    def test_wires_server_when_missing(self, bare_project: Path) -> None:
        report = add_resources(bare_project, ["docs://readme"])
        server = (_pkg(bare_project) / "server.py").read_text()
        assert "from .resources import RESOURCES, handle_resource_read" in server
        assert '"resources": {"subscribe": False, "listChanged": False},' in server
        assert 'if method == "resources/list":' in server
        assert any(p.name == "server.py" for p in report.changed_files)

    def test_already_wired_server_untouched(self, full_project: Path) -> None:
        before = (_pkg(full_project) / "server.py").read_text()
        report = add_resources(full_project, ["docs://guide"])
        assert (_pkg(full_project) / "server.py").read_text() == before
        assert not any(p.name == "server.py" for p in report.changed_files)

    def test_result_is_valid_python(self, bare_project: Path) -> None:
        add_resources(bare_project, ["docs://readme", "docs://guide"])
        ast.parse((_pkg(bare_project) / "resources.py").read_text())
        ast.parse((_pkg(bare_project) / "server.py").read_text())
        ast.parse(_tests_source(bare_project))

    def test_rejects_duplicate_existing(self, full_project: Path) -> None:
        with pytest.raises(AugmentError, match="already defined"):
            add_resources(full_project, ["docs://readme"])

    def test_rejects_duplicate_request(self, bare_project: Path) -> None:
        with pytest.raises(AugmentError, match="Duplicate resource URIs"):
            add_resources(bare_project, ["docs://a", "docs://a"])

    def test_extends_existing_test_assertion(self, full_project: Path) -> None:
        add_resources(full_project, ["docs://guide"])
        tests = _tests_source(full_project)
        assert '"docs://readme", "docs://guide"' in tests
        assert "def test_resource_read_docs_guide()" in tests
        assert tests.count("def test_unknown_resource_returns_error()") == 1

    def test_appends_test_block_when_missing(self, bare_project: Path) -> None:
        add_resources(bare_project, ["docs://readme"])
        tests = _tests_source(bare_project)
        assert "def test_resources_list()" in tests
        assert "def test_unknown_resource_returns_error()" in tests
        assert "def test_resource_read_docs_readme()" in tests

    def test_added_resource_serves_end_to_end(self, bare_project: Path) -> None:
        add_resources(bare_project, ["docs://readme"])
        resp = _rpc_via_subprocess(
            bare_project, "resources/read", {"uri": "docs://readme"}
        )
        assert resp["result"]["contents"][0]["uri"] == "docs://readme"

    def test_generated_pytest_suite_passes(self, bare_project: Path) -> None:
        add_resources(bare_project, ["docs://readme"])
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=bare_project,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# add_prompts
# ---------------------------------------------------------------------------


class TestAddPrompts:
    def test_updates_registry_dispatch_and_handler(self, full_project: Path) -> None:
        report = add_prompts(full_project, ["brainstorm"])
        source = (_pkg(full_project) / "prompts.py").read_text()
        assert existing_prompt_names(source) == ["summarize", "brainstorm"]
        assert 'if name == "brainstorm":' in source
        assert "async def _prompt_brainstorm(" in source
        assert report.added == ["brainstorm"]

    def test_wires_server_when_missing(self, bare_project: Path) -> None:
        report = add_prompts(bare_project, ["summarize"])
        server = (_pkg(bare_project) / "server.py").read_text()
        assert "from .prompts import PROMPTS, handle_get_prompt" in server
        assert '"prompts": {"listChanged": False},' in server
        assert 'if method == "prompts/get":' in server
        assert any(p.name == "server.py" for p in report.changed_files)

    def test_already_wired_server_untouched(self, full_project: Path) -> None:
        before = (_pkg(full_project) / "server.py").read_text()
        add_prompts(full_project, ["brainstorm"])
        assert (_pkg(full_project) / "server.py").read_text() == before

    def test_result_is_valid_python(self, bare_project: Path) -> None:
        add_prompts(bare_project, ["summarize", "brainstorm"])
        ast.parse((_pkg(bare_project) / "prompts.py").read_text())
        ast.parse((_pkg(bare_project) / "server.py").read_text())
        ast.parse(_tests_source(bare_project))

    def test_rejects_duplicate_existing(self, full_project: Path) -> None:
        with pytest.raises(AugmentError, match="already defined"):
            add_prompts(full_project, ["summarize"])

    def test_rejects_invalid_name(self, bare_project: Path) -> None:
        with pytest.raises(AugmentError, match="Invalid prompt name"):
            add_prompts(bare_project, ["bad-name"])

    def test_rejects_duplicate_request(self, bare_project: Path) -> None:
        with pytest.raises(AugmentError, match="Duplicate prompt names"):
            add_prompts(bare_project, ["a", "a"])

    def test_extends_existing_test_assertion(self, full_project: Path) -> None:
        add_prompts(full_project, ["brainstorm"])
        tests = _tests_source(full_project)
        assert '"summarize", "brainstorm"' in tests
        assert "def test_prompt_brainstorm_get()" in tests
        assert tests.count("def test_unknown_prompt_returns_error()") == 1

    def test_appends_test_block_when_missing(self, bare_project: Path) -> None:
        add_prompts(bare_project, ["summarize"])
        tests = _tests_source(bare_project)
        assert "def test_initialize_declares_prompts_capability()" in tests
        assert "def test_prompts_list_contains_scaffolded_prompts()" in tests
        assert "def test_unknown_prompt_returns_error()" in tests
        assert "def test_prompt_summarize_get()" in tests

    def test_added_prompt_serves_end_to_end(self, bare_project: Path) -> None:
        add_prompts(bare_project, ["summarize"])
        resp = _rpc_via_subprocess(
            bare_project, "prompts/get", {"name": "summarize", "arguments": {"topic": "LA"}}
        )
        text = resp["result"]["messages"][0]["content"]["text"]
        assert "Summarize prompt about LA" == text

    def test_generated_pytest_suite_passes(self, bare_project: Path) -> None:
        add_prompts(bare_project, ["summarize"])
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=bare_project,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# combined and CLI
# ---------------------------------------------------------------------------


class TestCombined:
    def test_add_both_to_bare_project_suite_passes(self, bare_project: Path) -> None:
        add_resources(bare_project, ["docs://readme"])
        add_prompts(bare_project, ["summarize"])
        server = (_pkg(bare_project) / "server.py").read_text()
        assert 'if method == "resources/read":' in server
        assert 'if method == "prompts/get":' in server
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=bare_project,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestCli:
    def test_cli_add_resource(self, bare_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["add", "resource", "docs://readme", "--project-dir", str(bare_project)]
        )
        assert result.exit_code == 0
        assert "docs://readme" in result.output
        assert "Wired resources capability" in result.output

    def test_cli_add_prompt(self, bare_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["add", "prompt", "summarize", "--project-dir", str(bare_project)]
        )
        assert result.exit_code == 0
        assert "summarize" in result.output

    def test_cli_add_resource_invalid_uri_fails(self, bare_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["add", "resource", "not-a-uri", "--project-dir", str(bare_project)]
        )
        assert result.exit_code == 1
        assert "Invalid resource URI" in result.output

    def test_cli_add_prompt_duplicate_fails(self, full_project: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["add", "prompt", "summarize", "--project-dir", str(full_project)]
        )
        assert result.exit_code == 1
        assert "already defined" in result.output
