"""Local MCP test client - send JSON-RPC requests and validate responses."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table


@dataclass
class TestResult:
    """Result of a single test case."""

    name: str
    passed: bool
    message: str = ""
    response: dict[str, Any] | None = None


@dataclass
class TestReport:
    """Aggregate test report."""

    results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)


class MCPTestClient:
    """Test client that communicates with an MCP server over stdio."""

    def __init__(self, server_cmd: list[str], cwd: Path | None = None) -> None:
        self.server_cmd = server_cmd
        self.cwd = cwd
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0

    def start(self) -> None:
        """Start the server process."""
        self._process = subprocess.Popen(
            self.server_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.cwd,
        )

    def stop(self) -> None:
        """Stop the server process."""
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None

    def send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and return the response."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("Server not started")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        data = json.dumps(request) + "\n"
        self._process.stdin.write(data.encode())
        self._process.stdin.flush()

        line = self._process.stdout.readline()
        if not line:
            raise RuntimeError("No response from server")

        return json.loads(line.decode())

    def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("Server not started")

        notification: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            notification["params"] = params

        data = json.dumps(notification) + "\n"
        self._process.stdin.write(data.encode())
        self._process.stdin.flush()


def run_test_suite(server_cmd: list[str], cwd: Path | None = None) -> TestReport:
    """Run the standard MCP test suite against a server.

    Args:
        server_cmd: Command to start the server (e.g. ["python", "-m", "my_server.server"]).
        cwd: Working directory for the server process.

    Returns:
        TestReport with all results.
    """
    report = TestReport()
    client = MCPTestClient(server_cmd, cwd=cwd)

    try:
        client.start()
    except Exception as exc:
        report.results.append(TestResult("server_start", False, str(exc)))
        return report

    report.results.append(TestResult("server_start", True, "Server started successfully"))

    # Test: initialize
    try:
        resp = client.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-forge-tester", "version": "0.1.0"},
        })
        if "result" in resp:
            result = resp["result"]
            has_version = "protocolVersion" in result
            has_info = "serverInfo" in result
            has_caps = "capabilities" in result
            ok = has_version and has_info and has_caps
            msg = "initialize response valid" if ok else f"Missing fields: version={has_version} info={has_info} caps={has_caps}"
            report.results.append(TestResult("initialize", ok, msg, resp))
        else:
            report.results.append(TestResult("initialize", False, f"Error: {resp.get('error')}", resp))
    except Exception as exc:
        report.results.append(TestResult("initialize", False, str(exc)))

    # Test: tools/list
    try:
        resp = client.send_request("tools/list")
        if "result" in resp:
            tools = resp["result"].get("tools", [])
            ok = isinstance(tools, list)
            report.results.append(TestResult("tools/list", ok, f"Found {len(tools)} tools", resp))
        else:
            report.results.append(TestResult("tools/list", False, f"Error: {resp.get('error')}", resp))
    except Exception as exc:
        report.results.append(TestResult("tools/list", False, str(exc)))

    # Test: tools/call (first tool if available)
    try:
        resp = client.send_request("tools/list")
        tools = resp.get("result", {}).get("tools", [])
        if tools:
            tool_name = tools[0]["name"]
            resp2 = client.send_request("tools/call", {
                "name": tool_name,
                "arguments": {"query": "test"},
            })
            if "result" in resp2:
                content = resp2["result"].get("content", [])
                ok = len(content) > 0
                report.results.append(TestResult("tools/call", ok, f"Called '{tool_name}' successfully", resp2))
            else:
                report.results.append(TestResult("tools/call", False, f"Error: {resp2.get('error')}", resp2))
        else:
            report.results.append(TestResult("tools/call", True, "No tools to test (skipped)"))
    except Exception as exc:
        report.results.append(TestResult("tools/call", False, str(exc)))

    # Test: ping
    try:
        resp = client.send_request("ping")
        ok = "result" in resp
        report.results.append(TestResult("ping", ok, "Ping OK" if ok else f"Error: {resp.get('error')}", resp))
    except Exception as exc:
        report.results.append(TestResult("ping", False, str(exc)))

    # Test: unknown method returns error
    try:
        resp = client.send_request("nonexistent/method")
        ok = "error" in resp
        report.results.append(TestResult("unknown_method", ok, "Correctly returned error for unknown method" if ok else "Should have returned error", resp))
    except Exception as exc:
        report.results.append(TestResult("unknown_method", False, str(exc)))

    client.stop()
    report.results.append(TestResult("server_stop", True, "Server stopped cleanly"))

    return report


def print_report(report: TestReport, console: Console | None = None) -> None:
    """Pretty-print a test report using Rich."""
    console = console or Console()

    table = Table(title="MCP Forge Test Results", show_lines=True)
    table.add_column("Test", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    for result in report.results:
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        table.add_row(result.name, status, result.message)

    console.print(table)
    console.print(f"\n[bold]{report.passed}/{report.total} passed[/bold]", end="")
    if report.failed:
        console.print(f"  [red]{report.failed} failed[/red]")
    else:
        console.print("  [green]All tests passed![/green]")
