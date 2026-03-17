"""Extended tests for the tester module - MCPTestClient and run_test_suite.

Covers MCPTestClient lifecycle (start/stop/send_request/send_notification)
with mocked subprocess, and run_test_suite with various server responses.
"""

from __future__ import annotations

import json
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from mcp_forge.tester import (
    MCPTestClient,
    TestReport,
    TestResult,
    print_report,
    run_test_suite,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_process(responses: list[dict] | None = None) -> MagicMock:
    """Create a mock subprocess.Popen with pre-loaded stdout responses."""
    proc = MagicMock()
    proc.stdin = MagicMock()
    proc.stderr = MagicMock()

    if responses:
        lines = [json.dumps(r).encode() + b"\n" for r in responses]
        proc.stdout = BytesIO(b"".join(lines))
    else:
        proc.stdout = BytesIO(b"")

    proc.wait.return_value = 0
    proc.terminate.return_value = None
    return proc


def _jsonrpc_result(id: int, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_error(id: int, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# MCPTestClient tests
# ---------------------------------------------------------------------------


class TestMCPTestClientStart:
    @patch("mcp_forge.tester.subprocess.Popen")
    def test_start_creates_process(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process()
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "-m", "server"])
        client.start()

        mock_popen.assert_called_once()
        assert client._process is proc

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_start_with_cwd(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process()
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"], cwd=Path("/tmp/project"))
        client.start()

        call_kwargs = mock_popen.call_args
        assert call_kwargs.kwargs.get("cwd") == Path("/tmp/project") or call_kwargs[1].get("cwd") == Path("/tmp/project")

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_start_raises_propagates(self, mock_popen: MagicMock) -> None:
        mock_popen.side_effect = FileNotFoundError("not found")
        client = MCPTestClient(["nonexistent"])
        with pytest.raises(FileNotFoundError):
            client.start()


class TestMCPTestClientStop:
    @patch("mcp_forge.tester.subprocess.Popen")
    def test_stop_terminates_process(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process()
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()
        client.stop()

        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=5)
        assert client._process is None

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_stop_twice_is_safe(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process()
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()
        client.stop()
        client.stop()  # Should not raise

        # terminate called only once
        proc.terminate.assert_called_once()


class TestMCPTestClientSendRequest:
    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_request_basic(self, mock_popen: MagicMock) -> None:
        expected_response = _jsonrpc_result(1, {"protocolVersion": "2024-11-05"})
        proc = _make_mock_process([expected_response])
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        resp = client.send_request("initialize", {"protocolVersion": "2024-11-05"})
        assert resp["result"]["protocolVersion"] == "2024-11-05"

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_request_increments_id(self, mock_popen: MagicMock) -> None:
        responses = [
            _jsonrpc_result(1, {"a": 1}),
            _jsonrpc_result(2, {"b": 2}),
        ]
        proc = _make_mock_process(responses)
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        client.send_request("method1")
        assert client._request_id == 1

        client.send_request("method2")
        assert client._request_id == 2

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_request_without_params(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process([_jsonrpc_result(1, {})])
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        resp = client.send_request("ping")
        assert "result" in resp

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_request_writes_to_stdin(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process([_jsonrpc_result(1, {})])
        # Override stdout to be readable but keep stdin mockable
        proc.stdout = BytesIO(json.dumps(_jsonrpc_result(1, {})).encode() + b"\n")
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        client.send_request("test_method", {"key": "value"})

        # Verify stdin.write was called
        proc.stdin.write.assert_called_once()
        written_data = proc.stdin.write.call_args[0][0]
        parsed = json.loads(written_data.decode())
        assert parsed["method"] == "test_method"
        assert parsed["params"] == {"key": "value"}
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_request_no_response_raises(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process()  # empty stdout
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        with pytest.raises(RuntimeError, match="No response"):
            client.send_request("initialize")

    def test_send_request_not_started_raises(self) -> None:
        client = MCPTestClient(["python", "srv.py"])
        with pytest.raises(RuntimeError, match="Server not started"):
            client.send_request("ping")

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_request_error_response(self, mock_popen: MagicMock) -> None:
        error_resp = _jsonrpc_error(1, -32601, "Method not found")
        proc = _make_mock_process([error_resp])
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        resp = client.send_request("nonexistent")
        assert "error" in resp
        assert resp["error"]["message"] == "Method not found"


class TestMCPTestClientSendNotification:
    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_notification_basic(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process()
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        client.send_notification("initialized")
        proc.stdin.write.assert_called_once()

        written = json.loads(proc.stdin.write.call_args[0][0].decode())
        assert written["method"] == "initialized"
        assert "id" not in written  # notifications have no id
        assert written["jsonrpc"] == "2.0"

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_notification_with_params(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process()
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        client.send_notification("progress", {"token": "abc", "value": 50})
        written = json.loads(proc.stdin.write.call_args[0][0].decode())
        assert written["params"]["token"] == "abc"

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_send_notification_without_params(self, mock_popen: MagicMock) -> None:
        proc = _make_mock_process()
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        client = MCPTestClient(["python", "srv.py"])
        client.start()

        client.send_notification("initialized")
        written = json.loads(proc.stdin.write.call_args[0][0].decode())
        assert "params" not in written

    def test_send_notification_not_started_raises(self) -> None:
        client = MCPTestClient(["python", "srv.py"])
        with pytest.raises(RuntimeError, match="Server not started"):
            client.send_notification("initialized")


# ---------------------------------------------------------------------------
# run_test_suite with mocked subprocess
# ---------------------------------------------------------------------------


class TestRunTestSuiteMocked:
    @patch("mcp_forge.tester.subprocess.Popen")
    def test_full_passing_suite(self, mock_popen: MagicMock) -> None:
        """Test run_test_suite with a server that responds correctly to all requests."""
        init_result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "test-server", "version": "1.0"},
        }
        tools_list_result = {
            "tools": [
                {
                    "name": "hello",
                    "description": "Says hello",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]
        }
        tool_call_result = {
            "content": [{"type": "text", "text": "Hello, world!"}]
        }
        ping_result = {}
        error_resp = _jsonrpc_error(6, -32601, "Method not found")

        responses = [
            _jsonrpc_result(1, init_result),       # initialize
            _jsonrpc_result(2, tools_list_result),  # tools/list
            _jsonrpc_result(3, tools_list_result),  # tools/list (for tools/call test)
            _jsonrpc_result(4, tool_call_result),   # tools/call
            _jsonrpc_result(5, ping_result),        # ping
            error_resp,                              # unknown method
        ]

        proc = _make_mock_process(responses)
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        report = run_test_suite(["python", "-m", "server"])

        assert report.total >= 7  # start + init + tools/list + tools/call + ping + unknown + stop
        assert report.failed == 0
        assert report.passed == report.total

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_server_returns_error_on_initialize(self, mock_popen: MagicMock) -> None:
        """If initialize returns an error, it should be marked as failed."""
        responses = [
            _jsonrpc_error(1, -32600, "Invalid request"),
            _jsonrpc_result(2, {"tools": []}),  # tools/list
            _jsonrpc_result(3, {"tools": []}),  # tools/list for call
            _jsonrpc_result(4, {}),              # ping
            _jsonrpc_error(5, -32601, "Not found"),  # unknown
        ]

        proc = _make_mock_process(responses)
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        report = run_test_suite(["python", "-m", "server"])

        init_result = next(r for r in report.results if r.name == "initialize")
        assert not init_result.passed

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_no_tools_skips_call(self, mock_popen: MagicMock) -> None:
        """If tools/list returns empty, tools/call should be skipped (pass)."""
        init_result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "t", "version": "0.1"},
        }
        responses = [
            _jsonrpc_result(1, init_result),
            _jsonrpc_result(2, {"tools": []}),   # tools/list
            _jsonrpc_result(3, {"tools": []}),   # tools/list for call check
            _jsonrpc_result(4, {}),              # ping
            _jsonrpc_error(5, -32601, "nope"),   # unknown
        ]

        proc = _make_mock_process(responses)
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        report = run_test_suite(["python", "-m", "server"])

        call_result = next(r for r in report.results if r.name == "tools/call")
        assert call_result.passed
        assert "skipped" in call_result.message.lower()

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_initialize_missing_fields(self, mock_popen: MagicMock) -> None:
        """Initialize response missing required fields should fail."""
        # Missing serverInfo
        bad_init = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
        }
        responses = [
            _jsonrpc_result(1, bad_init),
            _jsonrpc_result(2, {"tools": []}),
            _jsonrpc_result(3, {"tools": []}),
            _jsonrpc_result(4, {}),
            _jsonrpc_error(5, -32601, "nope"),
        ]

        proc = _make_mock_process(responses)
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        report = run_test_suite(["python", "-m", "server"])

        init_result = next(r for r in report.results if r.name == "initialize")
        assert not init_result.passed
        assert "Missing" in init_result.message

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_tool_call_returns_error(self, mock_popen: MagicMock) -> None:
        """If tools/call returns an error response, it should fail."""
        init_result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "t", "version": "0.1"},
        }
        tools = {"tools": [{"name": "broken", "description": "x", "inputSchema": {"type": "object"}}]}
        responses = [
            _jsonrpc_result(1, init_result),
            _jsonrpc_result(2, tools),
            _jsonrpc_result(3, tools),
            _jsonrpc_error(4, -32000, "Tool execution failed"),  # tools/call error
            _jsonrpc_result(5, {}),
            _jsonrpc_error(6, -32601, "nope"),
        ]

        proc = _make_mock_process(responses)
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        report = run_test_suite(["python", "-m", "server"])

        call_result = next(r for r in report.results if r.name == "tools/call")
        assert not call_result.passed

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_tool_call_empty_content(self, mock_popen: MagicMock) -> None:
        """If tools/call returns empty content array, it should fail."""
        init_result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "t", "version": "0.1"},
        }
        tools = {"tools": [{"name": "empty_tool", "description": "x", "inputSchema": {"type": "object"}}]}
        responses = [
            _jsonrpc_result(1, init_result),
            _jsonrpc_result(2, tools),
            _jsonrpc_result(3, tools),
            _jsonrpc_result(4, {"content": []}),  # empty content
            _jsonrpc_result(5, {}),
            _jsonrpc_error(6, -32601, "nope"),
        ]

        proc = _make_mock_process(responses)
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        report = run_test_suite(["python", "-m", "server"])

        call_result = next(r for r in report.results if r.name == "tools/call")
        assert not call_result.passed

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_ping_fails_with_error(self, mock_popen: MagicMock) -> None:
        """If ping returns an error, test should fail."""
        init_result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "t", "version": "0.1"},
        }
        responses = [
            _jsonrpc_result(1, init_result),
            _jsonrpc_result(2, {"tools": []}),
            _jsonrpc_result(3, {"tools": []}),
            _jsonrpc_error(4, -32601, "Ping not supported"),  # ping error
            _jsonrpc_result(5, {}),  # unknown method returns result (wrong)
        ]

        proc = _make_mock_process(responses)
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        report = run_test_suite(["python", "-m", "server"])

        ping_result = next(r for r in report.results if r.name == "ping")
        assert not ping_result.passed

    @patch("mcp_forge.tester.subprocess.Popen")
    def test_unknown_method_returns_result_fails(self, mock_popen: MagicMock) -> None:
        """If unknown method returns a result instead of error, test should fail."""
        init_result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "serverInfo": {"name": "t", "version": "0.1"},
        }
        responses = [
            _jsonrpc_result(1, init_result),
            _jsonrpc_result(2, {"tools": []}),
            _jsonrpc_result(3, {"tools": []}),
            _jsonrpc_result(4, {}),               # ping OK
            _jsonrpc_result(5, {"unexpected": 1}), # unknown method returns result (BAD)
        ]

        proc = _make_mock_process(responses)
        proc.stdin = MagicMock()
        mock_popen.return_value = proc

        report = run_test_suite(["python", "-m", "server"])

        unknown_result = next(r for r in report.results if r.name == "unknown_method")
        assert not unknown_result.passed


class TestRunTestSuiteExceptions:
    @patch("mcp_forge.tester.subprocess.Popen")
    def test_initialize_exception(self, mock_popen: MagicMock) -> None:
        """If reading from stdout raises, test should fail gracefully."""
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stderr = MagicMock()
        proc.stdout = MagicMock()
        proc.stdout.readline.side_effect = Exception("Broken pipe")
        proc.terminate.return_value = None
        proc.wait.return_value = 0
        mock_popen.return_value = proc

        report = run_test_suite(["python", "srv.py"])

        init_result = next(r for r in report.results if r.name == "initialize")
        assert not init_result.passed
        assert "Broken pipe" in init_result.message


# ---------------------------------------------------------------------------
# print_report edge cases
# ---------------------------------------------------------------------------


class TestPrintReportExtended:
    def test_print_empty_report(self) -> None:
        output = StringIO()
        console = Console(file=output, no_color=True, force_terminal=False)
        report = TestReport()
        print_report(report, console)
        text = output.getvalue()
        assert "0/0 passed" in text

    def test_print_report_shows_test_names(self) -> None:
        output = StringIO()
        console = Console(file=output, no_color=True, force_terminal=False)
        report = TestReport(results=[
            TestResult("server_start", True, "OK"),
            TestResult("initialize", True, "Valid"),
            TestResult("tools/list", False, "Timeout"),
        ])
        print_report(report, console)
        text = output.getvalue()
        assert "server_start" in text
        assert "initialize" in text
        assert "tools/list" in text
        assert "Timeout" in text

    def test_print_report_all_failed(self) -> None:
        output = StringIO()
        console = Console(file=output, no_color=True, force_terminal=False)
        report = TestReport(results=[
            TestResult("a", False, "err1"),
            TestResult("b", False, "err2"),
        ])
        print_report(report, console)
        text = output.getvalue()
        assert "0/2 passed" in text
        assert "2 failed" in text
