"""Integration tests for the full mcp-forge workflow.

Tests the scaffold -> validate -> inspect cycle to ensure
generated projects are valid out of the box.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from mcp_forge.cli import cli
from mcp_forge.scaffold import scaffold_project
from mcp_forge.validator import validate_project_structure


class TestFullWorkflow:
    """End-to-end scaffold -> validate workflow."""

    def test_scaffold_then_validate(self, tmp_path: Path) -> None:
        """A freshly scaffolded project should pass validation."""
        project = scaffold_project("demo-server", output_dir=tmp_path)
        report = validate_project_structure(project)
        assert report.is_valid
        assert len(report.errors) == 0

    def test_scaffold_with_tools_then_validate(self, tmp_path: Path) -> None:
        """Scaffolded project with custom tools should validate."""
        project = scaffold_project(
            "tool-server", output_dir=tmp_path, tools=["search", "translate"]
        )
        report = validate_project_structure(project)
        assert report.is_valid

    def test_scaffold_with_resources_then_validate(self, tmp_path: Path) -> None:
        """Scaffolded project with resources should validate."""
        project = scaffold_project(
            "resource-server",
            output_dir=tmp_path,
            resources=["file://data", "http://api"],
        )
        report = validate_project_structure(project)
        assert report.is_valid

    def test_scaffold_files_are_importable(self, tmp_path: Path) -> None:
        """Generated Python files should be syntactically valid."""
        project = scaffold_project("importable-server", output_dir=tmp_path)
        pkg = project / "src" / "importable_server"
        for py_file in pkg.glob("*.py"):
            code = py_file.read_text()
            compile(code, str(py_file), "exec")  # Syntax check

    def test_scaffold_pyproject_has_correct_name(self, tmp_path: Path) -> None:
        """Generated pyproject.toml should reference the project name."""
        project = scaffold_project("named-server", output_dir=tmp_path)
        toml_text = (project / "pyproject.toml").read_text()
        assert "named-server" in toml_text or "named_server" in toml_text

    def test_scaffold_readme_has_project_name(self, tmp_path: Path) -> None:
        """Generated README should contain the project name."""
        project = scaffold_project("readme-server", output_dir=tmp_path)
        readme = (project / "README.md").read_text()
        assert "readme-server" in readme.lower() or "readme server" in readme.lower()


class TestCLIIntegration:
    """Test CLI commands via CliRunner and subprocess."""

    def test_cli_new_then_validate(self, tmp_path: Path) -> None:
        """CLI new + validate should work end-to-end."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "new", "cli-server", "--tools", "search",
            "--output-dir", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Project created" in result.output

        result = runner.invoke(cli, ["validate", str(tmp_path / "cli-server")])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_cli_new_with_all_options(self, tmp_path: Path) -> None:
        """CLI new with all options should succeed."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "new", "full-server",
            "--tools", "weather,search,translate",
            "--resources", "file://data,http://api",
            "--description", "A fully configured server",
            "--author", "Test Author",
            "--output-dir", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "full-server" in result.output

    def test_validate_invalid_dir(self, tmp_path: Path) -> None:
        """Validating an empty directory should fail."""
        empty = tmp_path / "empty"
        empty.mkdir()
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(empty)])
        assert result.exit_code != 0

    def test_subprocess_version(self) -> None:
        """mcp-forge --version should work as subprocess."""
        result = subprocess.run(
            [sys.executable, "-m", "mcp_forge.cli", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "0.1.1" in result.stdout

    def test_subprocess_new(self, tmp_path: Path) -> None:
        """mcp-forge new should work as subprocess."""
        result = subprocess.run(
            [sys.executable, "-m", "mcp_forge.cli", "new", "sub-server",
             "--output-dir", str(tmp_path)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert (tmp_path / "sub-server" / "src").exists()

    def test_subprocess_validate(self, tmp_path: Path) -> None:
        """mcp-forge validate should work as subprocess."""
        scaffold_project("sub-validate", output_dir=tmp_path)
        result = subprocess.run(
            [sys.executable, "-m", "mcp_forge.cli", "validate", str(tmp_path / "sub-validate")],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "valid" in result.stdout.lower()


class TestGeneratedProjectQuality:
    """Test that generated projects are well-formed."""

    def test_gitignore_has_common_entries(self, tmp_path: Path) -> None:
        """Generated .gitignore should exclude common patterns."""
        project = scaffold_project("gi-server", output_dir=tmp_path)
        gitignore = (project / ".gitignore").read_text()
        assert "__pycache__" in gitignore
        assert ".venv" in gitignore
        assert "*.pyc" in gitignore

    def test_dockerfile_uses_python(self, tmp_path: Path) -> None:
        """Generated Dockerfile should use Python base image."""
        project = scaffold_project("docker-server", output_dir=tmp_path)
        dockerfile = (project / "Dockerfile").read_text()
        assert "python" in dockerfile.lower()

    def test_tests_directory_exists(self, tmp_path: Path) -> None:
        """Generated project should have tests directory with test file."""
        project = scaffold_project("test-server", output_dir=tmp_path)
        test_dir = project / "tests"
        assert test_dir.exists()
        test_files = list(test_dir.glob("test_*.py"))
        assert len(test_files) == 1

    def test_init_file_exists(self, tmp_path: Path) -> None:
        """Package __init__.py should exist."""
        project = scaffold_project("init-server", output_dir=tmp_path)
        init = project / "src" / "init_server" / "__init__.py"
        assert init.exists()

    def test_server_has_mcp(self, tmp_path: Path) -> None:
        """server.py should reference MCP."""
        project = scaffold_project("mcp-check-server", output_dir=tmp_path)
        server = (project / "src" / "mcp_check_server" / "server.py").read_text()
        assert "mcp" in server.lower()
