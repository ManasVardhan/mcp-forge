"""Extended tests for the CLI module."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mcp_forge import __version__
from mcp_forge.cli import cli


class TestCLIGroup:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "MCP Forge" in result.output

    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_version_matches(self) -> None:
        assert __version__ == "0.1.1"


class TestNewCommand:
    def test_new_basic(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "demo-server", "-o", str(tmp_path)])
        assert result.exit_code == 0
        assert "Forging" in result.output
        assert (tmp_path / "demo-server").exists()

    def test_new_with_tools(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "new", "api-server", "-t", "search,translate", "-o", str(tmp_path)
        ])
        assert result.exit_code == 0
        tools_py = (tmp_path / "api-server" / "src" / "api_server" / "tools.py").read_text()
        assert "search" in tools_py
        assert "translate" in tools_py

    def test_new_with_resources(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "new", "res-server", "-r", "file://data,http://api", "-o", str(tmp_path)
        ])
        assert result.exit_code == 0

    def test_new_with_description(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "new", "desc-server", "-d", "A great server", "-o", str(tmp_path)
        ])
        assert result.exit_code == 0
        readme = (tmp_path / "desc-server" / "README.md").read_text()
        assert "A great server" in readme

    def test_new_with_author(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, [
            "new", "auth-server", "-a", "TestAuthor", "-o", str(tmp_path)
        ])
        assert result.exit_code == 0
        pyproject = (tmp_path / "auth-server" / "pyproject.toml").read_text()
        assert "TestAuthor" in pyproject

    def test_new_shows_next_steps(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "steps-server", "-o", str(tmp_path)])
        assert result.exit_code == 0
        assert "Next steps" in result.output
        assert "cd steps-server" in result.output
        assert "pip install" in result.output

    def test_new_shows_tree(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "tree-server", "-o", str(tmp_path)])
        assert result.exit_code == 0
        assert "server.py" in result.output
        assert "tools.py" in result.output


class TestValidateCommand:
    def test_validate_empty_dir_fails(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(empty)])
        assert result.exit_code == 1

    def test_validate_valid_project(self, tmp_path: Path) -> None:
        # First scaffold a project, then validate it
        runner = CliRunner()
        runner.invoke(cli, ["new", "valid-project", "-o", str(tmp_path)])
        result = runner.invoke(cli, ["validate", str(tmp_path / "valid-project")])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_missing_server_py(self, tmp_path: Path) -> None:
        # Create minimal structure without server.py
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        pkg = tmp_path / "src" / "my_pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        (pkg / "tools.py").write_text("")
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(tmp_path)])
        assert result.exit_code == 1


class TestPublishCommand:
    def test_publish_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["publish", "--help"])
        assert result.exit_code == 0
        assert "publish" in result.output.lower()


class TestTestCommand:
    def test_test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["test", "--help"])
        assert result.exit_code == 0
        assert "--cmd" in result.output
