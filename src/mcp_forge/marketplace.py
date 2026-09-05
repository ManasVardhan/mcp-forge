"""Template marketplace: browse and install MCP server templates.

A template is a JSON descriptor that parameterizes scaffolding: name,
version, description, author, plus the tools, resources, and prompts the
generated server starts with, and optional extra files written into the
project. Templates live in a registry, which is a JSON file reachable
three ways:

- the builtin registry packaged with mcp-forge
- a local path to a registry JSON file
- an HTTP(S) URL serving the same JSON

Registry format:

    {
      "registry_version": 1,
      "templates": [
        {
          "name": "api-client",
          "version": "1.0.0",
          "description": "...",
          "author": "...",
          "tools": ["fetch_url"],
          "resources": ["config://settings"],
          "prompts": [],
          "extra_files": {"NOTES.md": "content with {{project_name}}"}
        }
      ]
    }
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from importlib import resources as importlib_resources
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .augment import (
    AugmentError,
    existing_prompt_names,
    existing_resource_uris,
    existing_tool_names,
    find_package_dir,
)
from .scaffold import scaffold_project, snake_case, validate_project_name

REGISTRY_VERSION = 1
BUILTIN_REGISTRY = "builtin"
_FETCH_TIMEOUT = 15.0


class MarketplaceError(Exception):
    """Raised for registry or template problems with a user-facing message."""


@dataclass
class Template:
    """A single installable MCP server template."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    tools: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    extra_files: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Template:
        """Build a Template from registry JSON, validating shape."""
        if not isinstance(data, dict):
            raise MarketplaceError("Template entry must be a JSON object.")
        name = data.get("name")
        if not name or not isinstance(name, str):
            raise MarketplaceError("Template entry is missing a 'name' string.")
        for key in ("tools", "resources", "prompts"):
            value = data.get(key, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise MarketplaceError(
                    f"Template '{name}': '{key}' must be a list of strings."
                )
        extra_files = data.get("extra_files", {})
        if not isinstance(extra_files, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in extra_files.items()
        ):
            raise MarketplaceError(
                f"Template '{name}': 'extra_files' must map path strings to content strings."
            )
        return cls(
            name=name,
            version=str(data.get("version", "1.0.0")),
            description=str(data.get("description", "")),
            author=str(data.get("author", "")),
            tools=list(data.get("tools", [])),
            resources=list(data.get("resources", [])),
            prompts=list(data.get("prompts", [])),
            extra_files=dict(extra_files),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tools": list(self.tools),
            "resources": list(self.resources),
            "prompts": list(self.prompts),
            "extra_files": dict(self.extra_files),
        }


def _load_registry_text(source: str) -> str:
    """Fetch raw registry JSON text from builtin data, a URL, or a path."""
    if source == BUILTIN_REGISTRY:
        ref = importlib_resources.files("mcp_forge") / "templates" / "registry.json"
        return ref.read_text(encoding="utf-8")
    if source.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(source, timeout=_FETCH_TIMEOUT) as resp:  # noqa: S310
                body: bytes = resp.read()
                return body.decode("utf-8")
        except (urllib.error.URLError, OSError, UnicodeDecodeError) as exc:
            raise MarketplaceError(f"Could not fetch registry from {source}: {exc}")
    path = Path(source)
    if not path.is_file():
        raise MarketplaceError(f"Registry file not found: {source}")
    return path.read_text(encoding="utf-8")


def load_registry(source: str | None = None) -> list[Template]:
    """Load templates from a registry source.

    Args:
        source: 'builtin' or None for the packaged registry, an HTTP(S)
            URL, or a local file path.

    Returns:
        Templates in registry order.

    Raises:
        MarketplaceError: If the registry cannot be read or is malformed.
    """
    source = source or BUILTIN_REGISTRY
    text = _load_registry_text(source)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MarketplaceError(f"Registry at {source} is not valid JSON: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("templates"), list):
        raise MarketplaceError(
            f"Registry at {source} must be an object with a 'templates' list."
        )
    version = data.get("registry_version", REGISTRY_VERSION)
    if version != REGISTRY_VERSION:
        raise MarketplaceError(
            f"Registry at {source} has unsupported registry_version {version} "
            f"(supported: {REGISTRY_VERSION})."
        )
    templates = [Template.from_dict(entry) for entry in data["templates"]]
    seen: set[str] = set()
    for template in templates:
        if template.name in seen:
            raise MarketplaceError(
                f"Registry at {source} contains duplicate template '{template.name}'."
            )
        seen.add(template.name)
    return templates


def get_template(name: str, source: str | None = None) -> Template:
    """Look up one template by name.

    Raises:
        MarketplaceError: If the template is not in the registry.
    """
    templates = load_registry(source)
    for template in templates:
        if template.name == name:
            return template
    available = ", ".join(t.name for t in templates) or "(none)"
    raise MarketplaceError(
        f"Template '{name}' not found in registry. Available: {available}"
    )


def _render_placeholders(content: str, project_name: str) -> str:
    return content.replace("{{project_name}}", project_name).replace(
        "{{pkg_name}}", snake_case(project_name)
    )


def _safe_project_path(project_root: Path, rel_path: str) -> Path:
    """Resolve an extra_files path inside the project, rejecting escapes."""
    candidate = Path(rel_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise MarketplaceError(
            f"Template extra file path '{rel_path}' must be relative "
            "and stay inside the project."
        )
    resolved = (project_root / candidate).resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise MarketplaceError(
            f"Template extra file path '{rel_path}' escapes the project directory."
        )
    return resolved


def install_template(
    name: str,
    project_name: str | None = None,
    source: str | None = None,
    output_dir: Path | None = None,
    author: str = "",
    description: str = "",
) -> Path:
    """Install a template as a new MCP server project.

    Args:
        name: Template name in the registry.
        project_name: Name for the new project (defaults to the template name).
        source: Registry source (builtin, path, or URL).
        output_dir: Parent directory for the project. Defaults to cwd.
        author: Author override for pyproject.toml.
        description: Description override.

    Returns:
        Path to the generated project root.

    Raises:
        MarketplaceError: For registry, template, or extra file problems.
        ValueError: If the project name is invalid.
    """
    template = get_template(name, source)
    project_name = project_name or template.name
    validate_project_name(project_name)

    project_root = scaffold_project(
        name=project_name,
        output_dir=output_dir,
        tools=template.tools,
        resources=template.resources,
        prompts=template.prompts,
        description=description or template.description,
        author=author or template.author,
    )

    for rel_path, content in template.extra_files.items():
        dest = _safe_project_path(project_root, rel_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_render_placeholders(content, project_name), encoding="utf-8")

    return project_root


# ---------------------------------------------------------------------------
# template publish
# ---------------------------------------------------------------------------

_PYPROJECT_NAME_RE = re.compile(r'^name\s*=\s*"([^"]+)"', re.MULTILINE)
_PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_PYPROJECT_DESC_RE = re.compile(r'^description\s*=\s*"([^"]+)"', re.MULTILINE)
_PYPROJECT_AUTHOR_RE = re.compile(
    r'^authors\s*=\s*\[\s*\{\s*name\s*=\s*"([^"]+)"', re.MULTILINE
)


def _extract_placeholders(content: str, project_name: str) -> str:
    """Reverse placeholder rendering so installs can re-parameterize.

    Occurrences of the project name and its package name are replaced
    with {{project_name}} and {{pkg_name}} respectively.
    """
    pkg = snake_case(project_name)
    content = content.replace(project_name, "{{project_name}}")
    if pkg != project_name:
        content = content.replace(pkg, "{{pkg_name}}")
    return content


def build_template_from_project(
    project_root: Path,
    name: str | None = None,
    include: Sequence[str] = (),
) -> Template:
    """Build a registry Template from a scaffolded project directory.

    Reads project metadata from pyproject.toml and scans the generated
    source for tools, resources, and prompts. Files listed in ``include``
    are embedded as extra_files with the project name replaced by
    placeholders so installs can rename them.

    Args:
        project_root: Root of a project created by ``mcp-forge new``.
        name: Template name override. Defaults to the project name.
        include: Project-relative paths of extra files to embed.

    Returns:
        A Template ready to publish.

    Raises:
        MarketplaceError: If the project layout, metadata, or include
            paths are invalid.
    """
    project_root = Path(project_root)
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.is_file():
        raise MarketplaceError(
            f"No pyproject.toml found in {project_root}. "
            "Run this on a project created by 'mcp-forge new'."
        )
    toml_text = pyproject_path.read_text(encoding="utf-8")
    name_match = _PYPROJECT_NAME_RE.search(toml_text)
    if not name_match:
        raise MarketplaceError(
            f"Could not read a project name from {pyproject_path}."
        )
    project_name = name_match.group(1)

    try:
        package_dir = find_package_dir(project_root)
    except AugmentError as exc:
        raise MarketplaceError(str(exc))

    tools = existing_tool_names(
        (package_dir / "tools.py").read_text(encoding="utf-8")
    )
    resources_path = package_dir / "resources.py"
    resources = (
        existing_resource_uris(resources_path.read_text(encoding="utf-8"))
        if resources_path.is_file()
        else []
    )
    prompts_path = package_dir / "prompts.py"
    prompts = (
        existing_prompt_names(prompts_path.read_text(encoding="utf-8"))
        if prompts_path.is_file()
        else []
    )

    extra_files: dict[str, str] = {}
    for rel_path in include:
        source_path = _safe_project_path(project_root, rel_path)
        if not source_path.is_file():
            raise MarketplaceError(
                f"Included file '{rel_path}' does not exist in {project_root}."
            )
        try:
            content = source_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise MarketplaceError(
                f"Included file '{rel_path}' is not UTF-8 text. "
                "Templates can only ship text files."
            )
        key = Path(rel_path).as_posix()
        extra_files[key] = _extract_placeholders(content, project_name)

    version_match = _PYPROJECT_VERSION_RE.search(toml_text)
    desc_match = _PYPROJECT_DESC_RE.search(toml_text)
    author_match = _PYPROJECT_AUTHOR_RE.search(toml_text)

    return Template(
        name=name or project_name,
        version=version_match.group(1) if version_match else "1.0.0",
        description=desc_match.group(1) if desc_match else "",
        author=author_match.group(1) if author_match else "",
        tools=tools,
        resources=resources,
        prompts=prompts,
        extra_files=extra_files,
    )


def publish_template(
    template: Template,
    registry_path: Path,
    force: bool = False,
) -> Path:
    """Add or replace a template entry in a local registry file.

    The registry file is created if it does not exist. Existing entries
    are preserved; an entry with the same name is only replaced when
    ``force`` is true.

    Args:
        template: The template to publish.
        registry_path: Local registry JSON file to write.
        force: Replace an existing entry with the same name.

    Returns:
        The registry path that was written.

    Raises:
        MarketplaceError: If the existing registry is malformed or the
            template name is already taken and force is false.
    """
    registry_path = Path(registry_path)
    existing = load_registry(str(registry_path)) if registry_path.is_file() else []

    published: list[Template] = []
    replaced = False
    for entry in existing:
        if entry.name == template.name:
            if not force:
                raise MarketplaceError(
                    f"Template '{template.name}' already exists in "
                    f"{registry_path}. Use --force to replace it."
                )
            published.append(template)
            replaced = True
        else:
            published.append(entry)
    if not replaced:
        published.append(template)

    payload = {
        "registry_version": REGISTRY_VERSION,
        "templates": [entry.to_dict() for entry in published],
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return registry_path
