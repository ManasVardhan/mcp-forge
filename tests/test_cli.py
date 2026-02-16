"""Tests for the CLI module."""

from click.testing import CliRunner

from mcp_forge.cli import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_new(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["new", "my-test-server", "--output-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "my-test-server" / "src" / "my_test_server" / "server.py").exists()


def test_cli_new_with_tools(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["new", "my-server", "-t", "weather,calc", "-o", str(tmp_path)])
    assert result.exit_code == 0
    tools_py = (tmp_path / "my-server" / "src" / "my_server" / "tools.py").read_text()
    assert "weather" in tools_py
    assert "calc" in tools_py


def test_cli_validate_missing_dir(tmp_path):
    runner = CliRunner()
    empty = tmp_path / "empty"
    empty.mkdir()
    result = runner.invoke(cli, ["validate", str(empty)])
    assert result.exit_code == 1
