"""Add tools to an existing scaffolded MCP server project.

``mcp-forge new`` generates a project once; this module lets users grow
that project later without hand-editing boilerplate. ``add_tools``
updates the generated ``tools.py`` (TOOLS registry, dispatch branch,
handler stub) and keeps the generated test harness in sync (expected
tools/list names plus one call test per new tool).

The edits are text-based and target the structure that the scaffolder
emits. Files that users have reshaped beyond recognition are rejected
with a clear error instead of being corrupted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .scaffold import validate_tool_names

_HANDLER_DEF_RE = re.compile(r"^async def _tool_([a-zA-Z][a-zA-Z0-9_]*)\(", re.MULTILINE)
_DISPATCH_RAISE = 'raise ValueError(f"Unknown tool: {name}")'
_NAMES_ASSERT_RE = re.compile(
    r"(def test_tools_list_contains_scaffolded_tools\(\).*?assert names == \[)([^\]]*)(\])",
    re.DOTALL,
)


class AugmentError(Exception):
    """Raised when a project cannot be augmented safely."""


@dataclass
class AddReport:
    """What ``add_tools`` changed."""

    package: str
    added: list[str]
    changed_files: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def find_package_dir(project_root: Path) -> Path:
    """Locate the generated package directory containing ``tools.py``.

    Args:
        project_root: Root of a project created by ``mcp-forge new``.

    Returns:
        The package directory under ``src/``.

    Raises:
        AugmentError: If the layout does not look like a scaffolded project.
    """
    src = project_root / "src"
    if not src.is_dir():
        raise AugmentError(
            f"No src/ directory in {project_root}. "
            "Run this inside a project created by 'mcp-forge new'."
        )
    candidates = [p.parent for p in sorted(src.glob("*/tools.py"))]
    if not candidates:
        raise AugmentError(
            f"No src/<package>/tools.py found in {project_root}. "
            "Run this inside a project created by 'mcp-forge new'."
        )
    if len(candidates) > 1:
        names = ", ".join(c.name for c in candidates)
        raise AugmentError(f"Multiple candidate packages found ({names}); cannot choose.")
    return candidates[0]


def existing_tool_names(tools_source: str) -> list[str]:
    """Extract tool names from a generated ``tools.py`` source string."""
    return _HANDLER_DEF_RE.findall(tools_source)


def _tools_entry(name: str) -> str:
    pretty = name.replace("_", " ").title()
    return (
        "    {\n"
        f'        "name": "{name}",\n'
        f'        "description": "{pretty} tool",\n'
        '        "inputSchema": {\n'
        '            "type": "object",\n'
        '            "properties": {\n'
        '                "query": {\n'
        '                    "type": "string",\n'
        f'                    "description": "Input query for the {name} tool",\n'
        "                }\n"
        "            },\n"
        '            "required": ["query"],\n'
        "        },\n"
        "    },\n"
    )


def _dispatch_branch(name: str) -> str:
    return f'    if name == "{name}":\n        return await _tool_{name}(arguments)\n'


def _handler_stub(name: str) -> str:
    return (
        f"async def _tool_{name}(arguments: dict[str, Any]) -> dict[str, Any]:\n"
        f"    \"\"\"Handle the '{name}' tool.\"\"\"\n"
        '    query = arguments.get("query", "")\n'
        "    return {\n"
        '        "content": [\n'
        "            {\n"
        '                "type": "text",\n'
        f'                "text": f"{name} result for: {{query}}",\n'
        "            }\n"
        "        ]\n"
        "    }\n"
    )


def _call_test(name: str) -> str:
    return (
        f"def test_tool_{name}_call() -> None:\n"
        "    response = rpc(\n"
        '        "tools/call",\n'
        f'        {{"name": "{name}", "arguments": {{"query": "test input"}}}},\n'
        "    )\n"
        '    content = response["result"]["content"]\n'
        '    assert content, "tool returned no content"\n'
        '    assert content[0]["type"] == "text"\n'
        '    assert "test input" in content[0]["text"]\n'
    )


def _augment_tools_source(source: str, names: Sequence[str]) -> str:
    """Insert registry entries, dispatch branches, and handlers for names."""
    registry_match = re.search(r"^TOOLS[^=]*= \[$", source, re.MULTILINE)
    if registry_match is None:
        raise AugmentError(
            "tools.py has no recognizable 'TOOLS ... = [' registry. "
            "Add the tool manually or restore the generated structure."
        )
    close_idx = source.find("\n]", registry_match.end())
    if close_idx == -1:
        raise AugmentError("tools.py TOOLS registry has no closing ']' at column 0.")
    insert_at = close_idx + 1
    entries = "".join(_tools_entry(n) for n in names)
    source = source[:insert_at] + entries + source[insert_at:]

    raise_idx = source.find(_DISPATCH_RAISE)
    if raise_idx == -1:
        raise AugmentError(
            "tools.py handle_tool_call has no recognizable 'raise ValueError' fallback. "
            "Add the dispatch branch manually or restore the generated structure."
        )
    line_start = source.rfind("\n", 0, raise_idx) + 1
    branches = "".join(_dispatch_branch(n) for n in names)
    source = source[:line_start] + branches + source[line_start:]

    if not source.endswith("\n"):
        source += "\n"
    source += "".join("\n\n" + _handler_stub(n) for n in names)
    return source


def _augment_tests_source(source: str, names: Sequence[str]) -> str:
    """Extend the expected tools/list names and append call tests."""
    match = _NAMES_ASSERT_RE.search(source)
    if match is not None:
        current = match.group(2).rstrip()
        additions = ", ".join(f'"{n}"' for n in names)
        combined = f"{current}, {additions}" if current else additions
        source = source[: match.start(2)] + combined + source[match.end(2) :]
    if not source.endswith("\n"):
        source += "\n"
    source += "".join("\n\n" + _call_test(n) for n in names)
    return source


def add_tools(project_root: Path, names: Sequence[str]) -> AddReport:
    """Add tool stubs to an existing scaffolded project.

    Args:
        project_root: Root of a project created by ``mcp-forge new``.
        names: New tool names (letters, digits, underscores).

    Returns:
        An :class:`AddReport` listing the files that were rewritten.

    Raises:
        AugmentError: If the project layout is unrecognizable, a name is
            invalid, or a tool with the same name already exists.
    """
    try:
        validate_tool_names(names)
    except ValueError as exc:
        raise AugmentError(str(exc)) from exc
    if len(set(names)) != len(names):
        raise AugmentError("Duplicate tool names in the request.")

    pkg_dir = find_package_dir(project_root)
    tools_path = pkg_dir / "tools.py"
    tools_source = tools_path.read_text(encoding="utf-8")

    existing = existing_tool_names(tools_source)
    clashes = sorted(set(names) & set(existing))
    if clashes:
        raise AugmentError(
            f"Tool(s) already defined in {tools_path.name}: {', '.join(clashes)}"
        )

    report = AddReport(package=pkg_dir.name, added=list(names))
    tools_path.write_text(_augment_tools_source(tools_source, names), encoding="utf-8")
    report.changed_files.append(tools_path)

    tests_path = project_root / "tests" / f"test_{pkg_dir.name}.py"
    if tests_path.is_file():
        tests_source = tests_path.read_text(encoding="utf-8")
        tests_path.write_text(_augment_tests_source(tests_source, names), encoding="utf-8")
        report.changed_files.append(tests_path)
    else:
        report.notes.append(f"No generated test file at {tests_path}; tests not updated.")
    return report
