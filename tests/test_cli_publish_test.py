"""Tests for CLI test and publish commands.

Covers the `mcp-forge test` and `mcp-forge publish` commands
with mocked subprocess and test suite.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from mcp_forge.cli import cli
from mcp_forge.tester import TestReport, TestResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_passing_report() -> TestReport:
    return TestReport(results=[
        TestResult("server_start", True, "OK"),
        TestResult("initialize", True, "Valid"),
        TestResult("tools/list", True, "Found 1 tool"),
        TestResult("tools/call", True, "Called 'hello'"),
        TestResult("ping", True, "Ping OK"),
        TestResult("unknown_method", True, "Error returned"),
        TestResult("server_stop", True, "Clean"),
    ])


def _make_failing_report() -> TestReport:
    return TestReport(results=[
        TestResult("server_start", True, "OK"),
        TestResult("initialize", False, "Missing fields"),
        TestResult("server_stop", True, "Clean"),
    ])


# ---------------------------------------------------------------------------
# mcp-forge test command
# ---------------------------------------------------------------------------


class TestTestCommand:
    @patch("mcp_forge.cli.run_test_suite")
    def test_test_passing(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _make_passing_report()
        runner = CliRunner()
        result = runner.invoke(cli, ["test", "--cmd", "python -m my_server.server"])
        assert result.exit_code == 0
        assert "Testing" in result.output

    @patch("mcp_forge.cli.run_test_suite")
    def test_test_failing_exits_1(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _make_failing_report()
        runner = CliRunner()
        result = runner.invoke(cli, ["test", "--cmd", "python -m my_server.server"])
        assert result.exit_code == 1

    @patch("mcp_forge.cli.run_test_suite")
    def test_test_with_cwd(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = _make_passing_report()
        runner = CliRunner()
        result = runner.invoke(cli, [
            "test",
            "--cmd", "python -m server",
            "--cwd", str(tmp_path),
        ])
        assert result.exit_code == 0
        # Verify cwd was passed
        call_kwargs = mock_run.call_args
        assert call_kwargs[1].get("cwd") == tmp_path or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] == tmp_path
        )

    def test_test_missing_cmd_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["test"])
        assert result.exit_code != 0
        assert "Missing" in result.output or "required" in result.output.lower()

    @patch("mcp_forge.cli.run_test_suite")
    def test_test_splits_cmd_string(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _make_passing_report()
        runner = CliRunner()
        runner.invoke(cli, ["test", "--cmd", "python -m my_server.server --port 8080"])

        call_args = mock_run.call_args[0][0]  # first positional arg = server_cmd
        assert call_args == ["python", "-m", "my_server.server", "--port", "8080"]


# ---------------------------------------------------------------------------
# mcp-forge publish command
# ---------------------------------------------------------------------------


class TestPublishCommand:
    @patch("mcp_forge.cli.subprocess.run")
    def test_publish_dry_run(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Dry run should build but not upload."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Create a minimal project dir
        project = tmp_path / "my-project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='test'")

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", str(project), "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output
        # Only build should be called, not twine
        assert mock_run.call_count == 1

    @patch("mcp_forge.cli.subprocess.run")
    def test_publish_build_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Build failure should exit with error."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="build error")

        project = tmp_path / "fail-project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='test'")

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", str(project)])
        assert result.exit_code == 1
        assert "Build failed" in result.output

    @patch("mcp_forge.cli.subprocess.run")
    def test_publish_upload_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Upload failure should exit with error."""
        # First call (build) succeeds, second call (upload) fails
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="", stderr=""),
            MagicMock(returncode=1, stdout="", stderr="auth error"),
        ]

        project = tmp_path / "upload-fail"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='test'")

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", str(project)])
        assert result.exit_code == 1
        assert "Upload failed" in result.output

    @patch("mcp_forge.cli.subprocess.run")
    def test_publish_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Successful build and upload."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        project = tmp_path / "good-project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='test'")

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", str(project)])
        assert result.exit_code == 0
        assert "Published" in result.output
        assert mock_run.call_count == 2  # build + upload

    @patch("mcp_forge.cli.subprocess.run")
    def test_publish_to_testpypi(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Publishing to testpypi should use the test URL."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        project = tmp_path / "testpypi-project"
        project.mkdir()
        (project / "pyproject.toml").write_text("[project]\nname='test'")

        runner = CliRunner()
        result = runner.invoke(cli, ["publish", str(project), "--repository", "testpypi"])
        assert result.exit_code == 0

        # Second call (upload) should use testpypi URL
        upload_call = mock_run.call_args_list[1]
        cmd_args = upload_call[0][0]
        assert "test.pypi.org" in " ".join(cmd_args)

    def test_publish_nonexistent_dir_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["publish", "/nonexistent/path/xyz"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# _print_tree (indirectly tested via new command output)
# ---------------------------------------------------------------------------


class TestPrintTree:
    def test_nested_tree_output(self, tmp_path: Path) -> None:
        """The new command should show nested tree structure."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "new", "tree-test",
            "--tools", "a,b,c",
            "--resources", "file://x",
            "-o", str(tmp_path),
        ])
        assert result.exit_code == 0
        # Should show generated structure
        assert "server.py" in result.output
        assert "tools.py" in result.output
        assert "resources.py" in result.output
        assert "Dockerfile" in result.output
