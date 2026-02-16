"""Project scaffolding - generates complete MCP server projects from templates."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, PackageLoader, select_autoescape


def get_template_env() -> Environment:
    """Create a Jinja2 environment that loads from the templates/ directory."""
    return Environment(
        loader=PackageLoader("mcp_forge", "templates"),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def snake_case(name: str) -> str:
    """Convert a project name like 'my-server' to 'my_server'."""
    return name.replace("-", "_").replace(" ", "_").lower()


def title_case(name: str) -> str:
    """Convert 'my-server' to 'My Server'."""
    return name.replace("-", " ").replace("_", " ").title()


def scaffold_project(
    name: str,
    output_dir: Path | None = None,
    tools: Sequence[str] = (),
    resources: Sequence[str] = (),
    description: str = "",
    author: str = "",
) -> Path:
    """Generate a complete MCP server project.

    Args:
        name: Project name (e.g. 'my-server').
        output_dir: Parent directory. Defaults to cwd.
        tools: List of tool names to scaffold.
        resources: List of resource URI patterns to scaffold.
        description: One-line project description.
        author: Author name for pyproject.toml.

    Returns:
        Path to the generated project root.
    """
    output_dir = output_dir or Path.cwd()
    project_root = output_dir / name
    pkg_name = snake_case(name)
    src_dir = project_root / "src" / pkg_name

    # Create directory structure
    for d in [
        src_dir,
        project_root / "tests",
    ]:
        d.mkdir(parents=True, exist_ok=True)

    env = get_template_env()

    context = {
        "project_name": name,
        "pkg_name": pkg_name,
        "title": title_case(name),
        "description": description or f"An MCP server: {title_case(name)}",
        "author": author or "Author",
        "tools": list(tools) if tools else ["hello"],
        "resources": list(resources) if resources else [],
    }

    # Map template files to output paths
    file_map: dict[str, Path] = {
        "server.py.j2": src_dir / "server.py",
        "tools.py.j2": src_dir / "tools.py",
        "resources.py.j2": src_dir / "resources.py",
        "init.py.j2": src_dir / "__init__.py",
        "project_pyproject.toml.j2": project_root / "pyproject.toml",
        "project_readme.md.j2": project_root / "README.md",
        "dockerfile.j2": project_root / "Dockerfile",
    }

    for template_name, dest_path in file_map.items():
        template = env.get_template(template_name)
        dest_path.write_text(template.render(**context))

    # Write a basic test file
    test_content = f'''"""Basic tests for {pkg_name}."""

import importlib


def test_import():
    mod = importlib.import_module("{pkg_name}")
    assert mod is not None


def test_server_module():
    mod = importlib.import_module("{pkg_name}.server")
    assert hasattr(mod, "mcp")
'''
    (project_root / "tests" / f"test_{pkg_name}.py").write_text(test_content)

    # Write .gitignore
    (project_root / ".gitignore").write_text(
        "__pycache__/\n*.pyc\n*.egg-info/\ndist/\nbuild/\n.venv/\n"
    )

    return project_root
