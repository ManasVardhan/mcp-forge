"""Tests for the auto-generated test harness in scaffolded projects.

Verifies that scaffold_project renders a real pytest suite with mock
JSON-RPC tool calls, and runs that suite end to end inside a generated
project to prove it passes out of the box.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from mcp_forge.scaffold import scaffold_project


def _generated_tests(project: Path, pkg: str) -> str:
    return (project / "tests" / f"test_{pkg}.py").read_text()


class TestHarnessContent:
    """Static checks on the generated test file."""

    def test_basic_tests_preserved(self, tmp_path: Path) -> None:
        project = scaffold_project("my-server", output_dir=tmp_path)
        content = _generated_tests(project, "my_server")
        assert "def test_import" in content
        assert "def test_server_module" in content

    def test_handshake_and_protocol_tests(self, tmp_path: Path) -> None:
        project = scaffold_project("my-server", output_dir=tmp_path)
        content = _generated_tests(project, "my_server")
        assert "def test_initialize_handshake" in content
        assert "def test_ping" in content
        assert "def test_request_id_is_echoed" in content
        assert "def test_tools_list_contains_scaffolded_tools" in content
        assert "def test_tool_schemas_declare_required_query" in content

    def test_per_tool_tests_generated(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "my-server", output_dir=tmp_path, tools=["weather", "calculator"]
        )
        content = _generated_tests(project, "my_server")
        assert "def test_tool_weather_call" in content
        assert "def test_tool_calculator_call" in content
        assert '"weather", "calculator"' in content

    def test_default_tool_test_generated(self, tmp_path: Path) -> None:
        project = scaffold_project("my-server", output_dir=tmp_path)
        content = _generated_tests(project, "my_server")
        assert "def test_tool_hello_call" in content

    def test_error_path_tests_generated(self, tmp_path: Path) -> None:
        project = scaffold_project("my-server", output_dir=tmp_path)
        content = _generated_tests(project, "my_server")
        assert "def test_unknown_tool_returns_error" in content
        assert "def test_unknown_method_returns_error" in content

    def test_resource_tests_generated_when_resources(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "my-server",
            output_dir=tmp_path,
            resources=["notes://all", "notes://recent"],
        )
        content = _generated_tests(project, "my_server")
        assert "def test_resources_list" in content
        assert "def test_resource_read_1" in content
        assert "def test_resource_read_2" in content
        assert "def test_unknown_resource_returns_error" in content

    def test_no_resource_tests_without_resources(self, tmp_path: Path) -> None:
        project = scaffold_project("my-server", output_dir=tmp_path)
        content = _generated_tests(project, "my_server")
        assert "test_resources_list" not in content
        assert "test_unknown_resource_returns_error" not in content

    def test_generated_file_compiles(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "my-server",
            output_dir=tmp_path,
            tools=["alpha", "beta"],
            resources=["data://x"],
        )
        content = _generated_tests(project, "my_server")
        compile(content, "test_my_server.py", "exec")

    def test_pyproject_has_dev_extra(self, tmp_path: Path) -> None:
        project = scaffold_project("my-server", output_dir=tmp_path)
        pyproject = (project / "pyproject.toml").read_text()
        assert "[project.optional-dependencies]" in pyproject
        assert 'dev = ["pytest"]' in pyproject


class TestHarnessExecution:
    """Run the generated suite for real inside a scaffolded project."""

    def _run_pytest(self, project: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(project / "src")
        return subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests"],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_generated_suite_passes(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "demo-server",
            output_dir=tmp_path,
            tools=["weather", "calculator"],
        )
        result = self._run_pytest(project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "11 passed" in result.stdout

    def test_generated_suite_passes_with_resources(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "res-server",
            output_dir=tmp_path,
            tools=["lookup"],
            resources=["notes://all"],
        )
        result = self._run_pytest(project)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "13 passed" in result.stdout
