"""Validate MCP server compliance - check required methods and schema validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

# JSON Schema for MCP tool definition
TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "description", "inputSchema"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "inputSchema": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {"type": "string", "const": "object"},
                "properties": {"type": "object"},
                "required": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

# JSON Schema for initialize response
INITIALIZE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["protocolVersion", "capabilities", "serverInfo"],
    "properties": {
        "protocolVersion": {"type": "string"},
        "capabilities": {"type": "object"},
        "serverInfo": {
            "type": "object",
            "required": ["name", "version"],
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
            },
        },
    },
}

# JSON Schema for tool call result
TOOL_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["content"],
    "properties": {
        "content": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {"type": "string", "enum": ["text", "image", "resource"]},
                },
            },
        },
        "isError": {"type": "boolean"},
    },
}

RESOURCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["uri", "name"],
    "properties": {
        "uri": {"type": "string", "minLength": 1},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "mimeType": {"type": "string"},
    },
}

PROMPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "arguments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "description": {"type": "string"},
                    "required": {"type": "boolean"},
                },
            },
        },
    },
}


@dataclass
class ValidationIssue:
    """A single validation issue."""

    level: str  # "error" or "warning"
    category: str
    message: str


@dataclass
class ValidationReport:
    """Full validation report."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, category: str, message: str) -> None:
        self.issues.append(ValidationIssue("error", category, message))

    def add_warning(self, category: str, message: str) -> None:
        self.issues.append(ValidationIssue("warning", category, message))

    def merge(self, other: "ValidationReport") -> None:
        """Absorb all issues from another report."""
        self.issues.extend(other.issues)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report for JSON output."""
        return {
            "valid": self.is_valid,
            "errors": [
                {"category": i.category, "message": i.message} for i in self.errors
            ],
            "warnings": [
                {"category": i.category, "message": i.message} for i in self.warnings
            ],
        }


def validate_project_structure(project_dir: Path) -> ValidationReport:
    """Validate that a project has the expected MCP server structure."""
    report = ValidationReport()

    # Check pyproject.toml exists
    if not (project_dir / "pyproject.toml").exists():
        report.add_error("structure", "Missing pyproject.toml")

    # Find the source package
    src_dir = project_dir / "src"
    if not src_dir.exists():
        report.add_error("structure", "Missing src/ directory")
        return report

    packages = [d for d in src_dir.iterdir() if d.is_dir() and (d / "__init__.py").exists()]
    if not packages:
        report.add_error("structure", "No Python package found in src/")
        return report

    pkg = packages[0]

    # Check required modules
    required_files = ["server.py", "tools.py"]
    for f in required_files:
        if not (pkg / f).exists():
            report.add_error("structure", f"Missing {f} in package")

    # Check optional but recommended files
    recommended = ["README.md", "Dockerfile", ".gitignore"]
    for f in recommended:
        if not (project_dir / f).exists():
            report.add_warning("structure", f"Missing recommended file: {f}")

    return report


def validate_tool_definitions(tools: list[dict[str, Any]]) -> ValidationReport:
    """Validate a list of tool definitions against the MCP schema."""
    report = ValidationReport()

    if not tools:
        report.add_warning("tools", "No tools defined")
        return report

    for i, tool in enumerate(tools):
        try:
            jsonschema.validate(tool, TOOL_SCHEMA)
        except jsonschema.ValidationError as exc:
            report.add_error("tools", f"Tool #{i} ({tool.get('name', '?')}): {exc.message}")

    # Check for duplicate names
    names = [t.get("name") for t in tools]
    seen: set[str] = set()
    for name in names:
        if name in seen:
            report.add_error("tools", f"Duplicate tool name: {name}")
        if name:
            seen.add(name)

    return report


def validate_resource_definitions(resources: list[dict[str, Any]]) -> ValidationReport:
    """Validate a list of resource definitions against the MCP schema."""
    report = ValidationReport()

    if not resources:
        return report

    for i, resource in enumerate(resources):
        try:
            jsonschema.validate(resource, RESOURCE_SCHEMA)
        except jsonschema.ValidationError as exc:
            report.add_error(
                "resources",
                f"Resource #{i} ({resource.get('name', '?')}): {exc.message}",
            )

    # Check for duplicate URIs
    uris = [r.get("uri") for r in resources]
    seen: set[str] = set()
    for uri in uris:
        if uri and uri in seen:
            report.add_error("resources", f"Duplicate resource URI: {uri}")
        if uri:
            seen.add(uri)

    return report


def validate_initialize_response(response: dict[str, Any]) -> ValidationReport:
    """Validate an initialize response."""
    report = ValidationReport()
    try:
        jsonschema.validate(response, INITIALIZE_RESPONSE_SCHEMA)
    except jsonschema.ValidationError as exc:
        report.add_error("initialize", exc.message)
    return report


def validate_tool_result(result: dict[str, Any]) -> ValidationReport:
    """Validate a tool call result."""
    report = ValidationReport()
    try:
        jsonschema.validate(result, TOOL_RESULT_SCHEMA)
    except jsonschema.ValidationError as exc:
        report.add_error("tool_result", exc.message)
    return report


def validate_prompt_definitions(prompts: list[dict[str, Any]]) -> ValidationReport:
    """Validate a list of prompt definitions against the MCP schema."""
    report = ValidationReport()

    if not prompts:
        return report

    for i, prompt in enumerate(prompts):
        try:
            jsonschema.validate(prompt, PROMPT_SCHEMA)
        except jsonschema.ValidationError as exc:
            report.add_error(
                "prompts",
                f"Prompt #{i} ({prompt.get('name', '?')}): {exc.message}",
            )

    # Check for duplicate names
    names = [p.get("name") for p in prompts]
    seen: set[str] = set()
    for name in names:
        if name and name in seen:
            report.add_error("prompts", f"Duplicate prompt name: {name}")
        if name:
            seen.add(name)

    return report


def validate_live_server(server_cmd: list[str], cwd: Path | None = None) -> ValidationReport:
    """Boot a server and validate its live protocol responses.

    Starts the server, performs the initialize handshake, then checks the
    initialize response, tool definitions, resource definitions, and prompt
    definitions against the MCP schemas. Also flags mismatches between
    declared capabilities and what the list endpoints actually return.
    """
    from .tester import MCPTestClient

    report = ValidationReport()
    client = MCPTestClient(server_cmd, cwd=cwd)

    try:
        client.start()
    except Exception as exc:
        report.add_error("startup", f"Failed to start server: {exc}")
        return report

    try:
        init_resp = client.send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-forge-validator", "version": "0"},
            },
        )
        if "error" in init_resp:
            report.add_error("initialize", f"initialize returned an error: {init_resp['error']}")
            return report

        init_result = init_resp.get("result", {})
        report.merge(validate_initialize_response(init_result))
        capabilities = init_result.get("capabilities", {})

        client.send_notification("notifications/initialized")

        # Tools
        tools_resp = client.send_request("tools/list")
        if "error" in tools_resp:
            tools: list[dict[str, Any]] = []
            if "tools" in capabilities:
                report.add_error(
                    "tools",
                    "Server declares the tools capability but tools/list returned an error",
                )
        else:
            tools = tools_resp.get("result", {}).get("tools", [])
            report.merge(validate_tool_definitions(tools))
            if tools and "tools" not in capabilities:
                report.add_warning(
                    "capabilities",
                    "Server returns tools but does not declare the tools capability",
                )

        # Resources
        resources_resp = client.send_request("resources/list")
        if "error" in resources_resp:
            if "resources" in capabilities:
                report.add_error(
                    "resources",
                    "Server declares the resources capability but resources/list "
                    "returned an error",
                )
        else:
            resources = resources_resp.get("result", {}).get("resources", [])
            report.merge(validate_resource_definitions(resources))
            if resources and "resources" not in capabilities:
                report.add_warning(
                    "capabilities",
                    "Server returns resources but does not declare the resources capability",
                )

        # Prompts
        prompts_resp = client.send_request("prompts/list")
        if "error" in prompts_resp:
            if "prompts" in capabilities:
                report.add_error(
                    "prompts",
                    "Server declares the prompts capability but prompts/list returned an error",
                )
        else:
            prompts = prompts_resp.get("result", {}).get("prompts", [])
            report.merge(validate_prompt_definitions(prompts))
            if prompts and "prompts" not in capabilities:
                report.add_warning(
                    "capabilities",
                    "Server returns prompts but does not declare the prompts capability",
                )

    except Exception as exc:
        report.add_error("protocol", f"Error communicating with server: {exc}")
    finally:
        client.stop()

    return report
