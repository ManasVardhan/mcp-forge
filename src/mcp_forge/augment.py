"""Add tools, resources, and prompts to an existing scaffolded MCP server project.

``mcp-forge new`` generates a project once; this module lets users grow
that project later without hand-editing boilerplate. ``add_tools``,
``add_resources``, and ``add_prompts`` update the generated package
modules (registry entries, dispatch branches, handler stubs), wire
server.py capabilities and dispatch when they are missing, and keep the
generated test harness in sync.

The edits are text-based and target the structure that the scaffolder
emits. Files that users have reshaped beyond recognition are rejected
with a clear error instead of being corrupted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .scaffold import validate_prompt_names, validate_tool_names

_HANDLER_DEF_RE = re.compile(r"^async def _tool_([a-zA-Z][a-zA-Z0-9_]*)\(", re.MULTILINE)
_DISPATCH_RAISE = 'raise ValueError(f"Unknown tool: {name}")'
_NAMES_ASSERT_RE = re.compile(
    r"(def test_tools_list_contains_scaffolded_tools\(\).*?assert names == \[)([^\]]*)(\])",
    re.DOTALL,
)

_PROMPT_HANDLER_DEF_RE = re.compile(
    r"^async def _prompt_([a-zA-Z][a-zA-Z0-9_]*)\(", re.MULTILINE
)
_PROMPT_DISPATCH_RAISE = 'raise ValueError(f"Unknown prompt: {name}")'
_PROMPT_NAMES_ASSERT_RE = re.compile(
    r"(def test_prompts_list_contains_scaffolded_prompts\(\).*?assert names == \[)"
    r"([^\]]*)(\])",
    re.DOTALL,
)
_RESOURCE_URI_RE = re.compile(r'^        "uri": "([^"]*)",$', re.MULTILINE)
_RESOURCE_URIS_ASSERT_RE = re.compile(
    r"(def test_resources_list\(\).*?assert uris == \[)([^\]]*)(\])", re.DOTALL
)
_VALID_RESOURCE_URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"\\]+$")

_TOOLS_IMPORT = "from .tools import TOOLS, handle_tool_call"
_RESOURCES_IMPORT = "from .resources import RESOURCES, handle_resource_read"
_PROMPTS_IMPORT = "from .prompts import PROMPTS, handle_get_prompt"
_TOOLS_CAPABILITY = '"tools": {"listChanged": False},'
_RESOURCES_CAPABILITY = '"resources": {"subscribe": False, "listChanged": False},'
_PROMPTS_CAPABILITY = '"prompts": {"listChanged": False},'
_PING_BRANCH = '        if method == "ping":'
_RESOURCE_BRANCHES = (
    '        if method == "resources/list":\n'
    '            return {"resources": RESOURCES}\n'
    '        if method == "resources/read":\n'
    '            return await handle_resource_read(params.get("uri", ""))\n'
)
_PROMPT_BRANCHES = (
    '        if method == "prompts/list":\n'
    '            return {"prompts": PROMPTS}\n'
    '        if method == "prompts/get":\n'
    "            return await handle_get_prompt(\n"
    '                params.get("name", ""), params.get("arguments", {})\n'
    "            )\n"
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


def _insert_registry_entries(
    source: str, registry: str, entries: str, filename: str
) -> str:
    """Insert entries before the closing bracket of a generated registry list."""
    registry_match = re.search(rf"^{registry}[^=]*= \[$", source, re.MULTILINE)
    if registry_match is None:
        raise AugmentError(
            f"{filename} has no recognizable '{registry} ... = [' registry. "
            "Add the entry manually or restore the generated structure."
        )
    close_idx = source.find("\n]", registry_match.end())
    if close_idx == -1:
        raise AugmentError(f"{filename} {registry} registry has no closing ']' at column 0.")
    insert_at = close_idx + 1
    return source[:insert_at] + entries + source[insert_at:]


def _insert_before_raise(source: str, raise_stmt: str, branches: str, where: str) -> str:
    """Insert dispatch branches before a generated 'raise ValueError' fallback."""
    raise_idx = source.find(raise_stmt)
    if raise_idx == -1:
        raise AugmentError(
            f"{where} has no recognizable 'raise ValueError' fallback. "
            "Add the dispatch branch manually or restore the generated structure."
        )
    line_start = source.rfind("\n", 0, raise_idx) + 1
    return source[:line_start] + branches + source[line_start:]


def _augment_tools_source(source: str, names: Sequence[str]) -> str:
    """Insert registry entries, dispatch branches, and handlers for names."""
    entries = "".join(_tools_entry(n) for n in names)
    source = _insert_registry_entries(source, "TOOLS", entries, "tools.py")

    branches = "".join(_dispatch_branch(n) for n in names)
    source = _insert_before_raise(
        source, _DISPATCH_RAISE, branches, "tools.py handle_tool_call"
    )

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

# ---------------------------------------------------------------------------
# server.py wiring shared by resources and prompts
# ---------------------------------------------------------------------------


def _wire_server(
    source: str, import_line: str, capability: str, marker: str, branches: str
) -> tuple[str, bool]:
    """Ensure server.py imports, declares, and dispatches a capability.

    Projects scaffolded without resources or prompts have none of the
    wiring; this adds the import line, the capability entry in the
    initialize response, and the dispatch branches before the ping
    handler. Already-wired servers are returned unchanged.

    Returns:
        The (possibly updated) source and whether anything changed.
    """
    if marker in source:
        return source, False

    idx = source.find(_TOOLS_IMPORT)
    if idx == -1:
        raise AugmentError(
            "server.py has no recognizable tools import line. "
            "Wire the capability manually or restore the generated structure."
        )
    end = idx + len(_TOOLS_IMPORT)
    source = source[:end] + "\n" + import_line + source[end:]

    cap_idx = source.find(_TOOLS_CAPABILITY)
    if cap_idx == -1:
        raise AugmentError(
            "server.py initialize response has no recognizable tools capability. "
            "Wire the capability manually or restore the generated structure."
        )
    cap_end = source.find("\n", cap_idx) + 1
    source = source[:cap_end] + "                    " + capability + "\n" + source[cap_end:]

    ping_idx = source.find(_PING_BRANCH)
    if ping_idx == -1:
        raise AugmentError(
            "server.py _dispatch has no recognizable ping branch. "
            "Wire the dispatch manually or restore the generated structure."
        )
    source = source[:ping_idx] + branches + source[ping_idx:]
    return source, True


# ---------------------------------------------------------------------------
# add resource
# ---------------------------------------------------------------------------


def validate_resource_uris(uris: Sequence[str]) -> None:
    """Validate resource URIs and raise AugmentError if any are invalid.

    URIs must look like ``scheme://path`` with no whitespace, quotes,
    or backslashes (they are inserted into generated source files).
    """
    for uri in uris:
        if not uri:
            raise AugmentError("Resource URI cannot be empty.")
        if not _VALID_RESOURCE_URI_RE.match(uri):
            raise AugmentError(
                f"Invalid resource URI '{uri}'. "
                "URIs must look like scheme://path with no spaces or quotes."
            )


def existing_resource_uris(resources_source: str) -> list[str]:
    """Extract resource URIs from a generated ``resources.py`` source string."""
    return _RESOURCE_URI_RE.findall(resources_source)


def _resource_entry(uri: str) -> str:
    name = uri.replace("://", " ").replace("/", " ").title()
    return (
        "    {\n"
        f'        "uri": "{uri}",\n'
        f'        "name": "{name}",\n'
        '        "mimeType": "text/plain",\n'
        "    },\n"
    )


def _resource_slug(uri: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", uri).strip("_")


def _resource_read_test(uri: str) -> str:
    return (
        f"def test_resource_read_{_resource_slug(uri)}() -> None:\n"
        f'    response = rpc("resources/read", {{"uri": "{uri}"}})\n'
        '    contents = response["result"]["contents"]\n'
        f'    assert contents[0]["uri"] == "{uri}"\n'
        '    assert contents[0]["text"]\n'
    )


def _resources_list_test(uris: Sequence[str]) -> str:
    quoted = ", ".join(f'"{u}"' for u in uris)
    return (
        "def test_resources_list() -> None:\n"
        '    response = rpc("resources/list")\n'
        '    uris = [res["uri"] for res in response["result"]["resources"]]\n'
        f"    assert uris == [{quoted}]\n"
    )


_UNKNOWN_RESOURCE_TEST = (
    "def test_unknown_resource_returns_error() -> None:\n"
    '    response = rpc("resources/read", {"uri": "bogus://nowhere"})\n'
    '    assert "error" in response\n'
)


def _augment_resource_tests(source: str, uris: Sequence[str]) -> str:
    """Extend the expected resources/list URIs and append read tests."""
    parts: list[str] = []
    match = _RESOURCE_URIS_ASSERT_RE.search(source)
    if match is not None:
        current = match.group(2).rstrip()
        additions = ", ".join(f'"{u}"' for u in uris)
        combined = f"{current}, {additions}" if current else additions
        source = source[: match.start(2)] + combined + source[match.end(2) :]
    else:
        parts.append(_resources_list_test(uris))
        parts.append(_UNKNOWN_RESOURCE_TEST)
    parts.extend(_resource_read_test(u) for u in uris)
    if not source.endswith("\n"):
        source += "\n"
    return source + "".join("\n\n" + p for p in parts)


def add_resources(project_root: Path, uris: Sequence[str]) -> AddReport:
    """Add resource stubs to an existing scaffolded project.

    Updates the generated ``resources.py`` registry, wires the
    resources capability into ``server.py`` when missing, and keeps the
    generated test harness in sync.

    Args:
        project_root: Root of a project created by ``mcp-forge new``.
        uris: New resource URIs (``scheme://path``).

    Returns:
        An :class:`AddReport` listing the files that were rewritten.

    Raises:
        AugmentError: If the project layout is unrecognizable, a URI is
            invalid, or a resource with the same URI already exists.
    """
    validate_resource_uris(uris)
    if len(set(uris)) != len(uris):
        raise AugmentError("Duplicate resource URIs in the request.")

    pkg_dir = find_package_dir(project_root)
    resources_path = pkg_dir / "resources.py"
    if not resources_path.is_file():
        raise AugmentError(
            f"No resources.py in {pkg_dir}. "
            "Run this inside a project created by 'mcp-forge new'."
        )
    resources_source = resources_path.read_text(encoding="utf-8")

    existing = existing_resource_uris(resources_source)
    clashes = sorted(set(uris) & set(existing))
    if clashes:
        raise AugmentError(
            f"Resource(s) already defined in {resources_path.name}: {', '.join(clashes)}"
        )

    report = AddReport(package=pkg_dir.name, added=list(uris))
    entries = "".join(_resource_entry(u) for u in uris)
    resources_path.write_text(
        _insert_registry_entries(resources_source, "RESOURCES", entries, "resources.py"),
        encoding="utf-8",
    )
    report.changed_files.append(resources_path)

    server_path = pkg_dir / "server.py"
    if server_path.is_file():
        server_source, changed = _wire_server(
            server_path.read_text(encoding="utf-8"),
            _RESOURCES_IMPORT,
            _RESOURCES_CAPABILITY,
            '"resources/list"',
            _RESOURCE_BRANCHES,
        )
        if changed:
            server_path.write_text(server_source, encoding="utf-8")
            report.changed_files.append(server_path)
            report.notes.append("Wired resources capability into server.py.")
    else:
        report.notes.append(f"No server.py at {server_path}; capability not wired.")

    tests_path = project_root / "tests" / f"test_{pkg_dir.name}.py"
    if tests_path.is_file():
        tests_source = tests_path.read_text(encoding="utf-8")
        tests_path.write_text(
            _augment_resource_tests(tests_source, uris), encoding="utf-8"
        )
        report.changed_files.append(tests_path)
    else:
        report.notes.append(f"No generated test file at {tests_path}; tests not updated.")
    return report


# ---------------------------------------------------------------------------
# add prompt
# ---------------------------------------------------------------------------


def existing_prompt_names(prompts_source: str) -> list[str]:
    """Extract prompt names from a generated ``prompts.py`` source string."""
    return _PROMPT_HANDLER_DEF_RE.findall(prompts_source)


def _prompt_entry(name: str) -> str:
    pretty = name.replace("_", " ").title()
    return (
        "    {\n"
        f'        "name": "{name}",\n'
        f'        "description": "{pretty} prompt",\n'
        '        "arguments": [\n'
        "            {\n"
        '                "name": "topic",\n'
        f'                "description": "Topic to focus the {name} prompt on",\n'
        '                "required": False,\n'
        "            }\n"
        "        ],\n"
        "    },\n"
    )


def _prompt_dispatch_branch(name: str) -> str:
    return f'    if name == "{name}":\n        return await _prompt_{name}(arguments)\n'


def _prompt_stub(name: str) -> str:
    pretty = name.replace("_", " ").title()
    return (
        f"async def _prompt_{name}(arguments: dict[str, Any]) -> dict[str, Any]:\n"
        f"    \"\"\"Build the '{name}' prompt messages.\"\"\"\n"
        '    topic = arguments.get("topic", "")\n'
        f'    text = "{pretty} prompt"\n'
        "    if topic:\n"
        '        text = f"{text} about {topic}"\n'
        "    return {\n"
        f'        "description": "{pretty} prompt",\n'
        '        "messages": [\n'
        "            {\n"
        '                "role": "user",\n'
        '                "content": {"type": "text", "text": text},\n'
        "            }\n"
        "        ],\n"
        "    }\n"
    )


def _prompt_get_test(name: str) -> str:
    return (
        f"def test_prompt_{name}_get() -> None:\n"
        "    response = rpc(\n"
        '        "prompts/get",\n'
        f'        {{"name": "{name}", "arguments": {{"topic": "unit testing"}}}},\n'
        "    )\n"
        '    messages = response["result"]["messages"]\n'
        '    assert messages, "prompt returned no messages"\n'
        '    assert messages[0]["role"] == "user"\n'
        '    assert "unit testing" in messages[0]["content"]["text"]\n'
    )


def _prompts_list_test(names: Sequence[str]) -> str:
    quoted = ", ".join(f'"{n}"' for n in names)
    return (
        "def test_prompts_list_contains_scaffolded_prompts() -> None:\n"
        '    response = rpc("prompts/list")\n'
        '    names = [prompt["name"] for prompt in response["result"]["prompts"]]\n'
        f"    assert names == [{quoted}]\n"
    )


_PROMPTS_CAPABILITY_TEST = (
    "def test_initialize_declares_prompts_capability() -> None:\n"
    '    response = rpc("initialize")\n'
    '    assert "prompts" in response["result"]["capabilities"]\n'
)

_UNKNOWN_PROMPT_TEST = (
    "def test_unknown_prompt_returns_error() -> None:\n"
    '    response = rpc("prompts/get", {"name": "no_such_prompt", "arguments": {}})\n'
    '    assert "error" in response\n'
    '    assert "no_such_prompt" in response["error"]["message"]\n'
)


def _augment_prompts_source(source: str, names: Sequence[str]) -> str:
    """Insert registry entries, dispatch branches, and handlers for prompts."""
    entries = "".join(_prompt_entry(n) for n in names)
    source = _insert_registry_entries(source, "PROMPTS", entries, "prompts.py")

    branches = "".join(_prompt_dispatch_branch(n) for n in names)
    source = _insert_before_raise(
        source, _PROMPT_DISPATCH_RAISE, branches, "prompts.py handle_get_prompt"
    )

    if not source.endswith("\n"):
        source += "\n"
    source += "".join("\n\n" + _prompt_stub(n) for n in names)
    return source


def _augment_prompt_tests(source: str, names: Sequence[str]) -> str:
    """Extend the expected prompts/list names and append get tests."""
    parts: list[str] = []
    match = _PROMPT_NAMES_ASSERT_RE.search(source)
    if match is not None:
        current = match.group(2).rstrip()
        additions = ", ".join(f'"{n}"' for n in names)
        combined = f"{current}, {additions}" if current else additions
        source = source[: match.start(2)] + combined + source[match.end(2) :]
    else:
        parts.append(_PROMPTS_CAPABILITY_TEST)
        parts.append(_prompts_list_test(names))
        parts.append(_UNKNOWN_PROMPT_TEST)
    parts.extend(_prompt_get_test(n) for n in names)
    if not source.endswith("\n"):
        source += "\n"
    return source + "".join("\n\n" + p for p in parts)


def add_prompts(project_root: Path, names: Sequence[str]) -> AddReport:
    """Add prompt stubs to an existing scaffolded project.

    Updates the generated ``prompts.py`` (PROMPTS registry, dispatch
    branch, handler stub), wires the prompts capability into
    ``server.py`` when missing, and keeps the generated test harness in
    sync.

    Args:
        project_root: Root of a project created by ``mcp-forge new``.
        names: New prompt names (letters, digits, underscores).

    Returns:
        An :class:`AddReport` listing the files that were rewritten.

    Raises:
        AugmentError: If the project layout is unrecognizable, a name is
            invalid, or a prompt with the same name already exists.
    """
    try:
        validate_prompt_names(names)
    except ValueError as exc:
        raise AugmentError(str(exc)) from exc
    if len(set(names)) != len(names):
        raise AugmentError("Duplicate prompt names in the request.")

    pkg_dir = find_package_dir(project_root)
    prompts_path = pkg_dir / "prompts.py"
    if not prompts_path.is_file():
        raise AugmentError(
            f"No prompts.py in {pkg_dir}. "
            "Run this inside a project created by 'mcp-forge new'."
        )
    prompts_source = prompts_path.read_text(encoding="utf-8")

    existing = existing_prompt_names(prompts_source)
    clashes = sorted(set(names) & set(existing))
    if clashes:
        raise AugmentError(
            f"Prompt(s) already defined in {prompts_path.name}: {', '.join(clashes)}"
        )

    report = AddReport(package=pkg_dir.name, added=list(names))
    prompts_path.write_text(
        _augment_prompts_source(prompts_source, names), encoding="utf-8"
    )
    report.changed_files.append(prompts_path)

    server_path = pkg_dir / "server.py"
    if server_path.is_file():
        server_source, changed = _wire_server(
            server_path.read_text(encoding="utf-8"),
            _PROMPTS_IMPORT,
            _PROMPTS_CAPABILITY,
            '"prompts/list"',
            _PROMPT_BRANCHES,
        )
        if changed:
            server_path.write_text(server_source, encoding="utf-8")
            report.changed_files.append(server_path)
            report.notes.append("Wired prompts capability into server.py.")
    else:
        report.notes.append(f"No server.py at {server_path}; capability not wired.")

    tests_path = project_root / "tests" / f"test_{pkg_dir.name}.py"
    if tests_path.is_file():
        tests_source = tests_path.read_text(encoding="utf-8")
        tests_path.write_text(_augment_prompt_tests(tests_source, names), encoding="utf-8")
        report.changed_files.append(tests_path)
    else:
        report.notes.append(f"No generated test file at {tests_path}; tests not updated.")
    return report
