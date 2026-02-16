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
