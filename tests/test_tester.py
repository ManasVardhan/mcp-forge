"""Tests for the MCP tester module."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_forge.tester import MCPTestClient, TestReport, TestResult, print_report, run_test_suite


class TestTestResult:
    def test_passed_result(self) -> None:
        r = TestResult(name="test1", passed=True, message="OK")
        assert r.passed
        assert r.name == "test1"
        assert r.message == "OK"
        assert r.response is None

    def test_failed_result(self) -> None:
        r = TestResult(name="test1", passed=False, message="Error occurred")
        assert not r.passed

    def test_result_with_response(self) -> None:
        resp = {"jsonrpc": "2.0", "id": 1, "result": {}}
        r = TestResult(name="test1", passed=True, response=resp)
        assert r.response == resp


class TestTestReport:
    def test_empty_report(self) -> None:
        report = TestReport()
        assert report.total == 0
        assert report.passed == 0
        assert report.failed == 0

    def test_all_passed(self) -> None:
        report = TestReport(results=[
            TestResult("a", True),
            TestResult("b", True),
            TestResult("c", True),
        ])
        assert report.total == 3
        assert report.passed == 3
        assert report.failed == 0

    def test_some_failed(self) -> None:
        report = TestReport(results=[
            TestResult("a", True),
            TestResult("b", False),
            TestResult("c", True),
        ])
        assert report.total == 3
        assert report.passed == 2
        assert report.failed == 1

    def test_all_failed(self) -> None:
        report = TestReport(results=[
            TestResult("a", False),
            TestResult("b", False),
        ])
        assert report.total == 2
        assert report.passed == 0
        assert report.failed == 2


class TestMCPTestClient:
    def test_client_init(self) -> None:
        client = MCPTestClient(["python", "-m", "server"])
        assert client.server_cmd == ["python", "-m", "server"]
        assert client.cwd is None
        assert client._process is None
        assert client._request_id == 0

    def test_client_with_cwd(self) -> None:
        client = MCPTestClient(["python", "server.py"], cwd=Path("/tmp"))
        assert client.cwd == Path("/tmp")

    def test_send_request_without_start_raises(self) -> None:
        client = MCPTestClient(["python", "server.py"])
        with pytest.raises(RuntimeError, match="Server not started"):
            client.send_request("initialize")

    def test_send_notification_without_start_raises(self) -> None:
        client = MCPTestClient(["python", "server.py"])
        with pytest.raises(RuntimeError, match="Server not started"):
            client.send_notification("initialized")

    def test_stop_without_start(self) -> None:
        client = MCPTestClient(["python", "server.py"])
        # Should not raise
        client.stop()
        assert client._process is None


class TestRunTestSuiteFailedStart:
    def test_server_fails_to_start(self) -> None:
        # Non-existent command
        report = run_test_suite(["nonexistent_command_12345"])
        assert report.failed > 0
        assert report.results[0].name == "server_start"
        assert not report.results[0].passed


class TestPrintReport:
    def test_print_all_passed(self) -> None:
        from rich.console import Console
        from io import StringIO

        output = StringIO()
        console = Console(file=output, no_color=True, force_terminal=False)

        report = TestReport(results=[
            TestResult("test1", True, "OK"),
            TestResult("test2", True, "OK"),
        ])
        print_report(report, console)
        text = output.getvalue()
        assert "2/2 passed" in text

    def test_print_with_failures(self) -> None:
        from rich.console import Console
        from io import StringIO

        output = StringIO()
        console = Console(file=output, no_color=True, force_terminal=False)

        report = TestReport(results=[
            TestResult("test1", True, "OK"),
            TestResult("test2", False, "Broken"),
        ])
        print_report(report, console)
        text = output.getvalue()
        assert "1/2 passed" in text
        assert "1 failed" in text

    def test_print_default_console(self) -> None:
        report = TestReport(results=[TestResult("test1", True, "OK")])
        # Should not raise with default console
        print_report(report)
