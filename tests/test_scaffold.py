"""Tests for the scaffold module."""

from pathlib import Path

import pytest

from mcp_forge.scaffold import scaffold_project, snake_case, title_case


def test_snake_case():
    assert snake_case("my-server") == "my_server"
    assert snake_case("My Server") == "my_server"
    assert snake_case("already_snake") == "already_snake"


def test_title_case():
    assert title_case("my-server") == "My Server"
    assert title_case("hello_world") == "Hello World"


def test_scaffold_creates_directory(tmp_path: Path):
    project = scaffold_project("test-server", output_dir=tmp_path)
    assert project.exists()
    assert project.name == "test-server"


def test_scaffold_creates_package_files(tmp_path: Path):
    project = scaffold_project("test-server", output_dir=tmp_path)
    pkg = project / "src" / "test_server"
    assert (pkg / "__init__.py").exists()
    assert (pkg / "server.py").exists()
    assert (pkg / "tools.py").exists()
    assert (pkg / "resources.py").exists()


def test_scaffold_creates_pyproject(tmp_path: Path):
    project = scaffold_project("test-server", output_dir=tmp_path)
    pyproject = project / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text()
    assert "test-server" in content


def test_scaffold_creates_readme(tmp_path: Path):
    project = scaffold_project("test-server", output_dir=tmp_path)
    readme = project / "README.md"
    assert readme.exists()
    assert "Test Server" in readme.read_text()


def test_scaffold_creates_dockerfile(tmp_path: Path):
    project = scaffold_project("test-server", output_dir=tmp_path)
    assert (project / "Dockerfile").exists()


def test_scaffold_with_tools(tmp_path: Path):
    project = scaffold_project("test-server", output_dir=tmp_path, tools=["weather", "calculator"])
    tools_py = (project / "src" / "test_server" / "tools.py").read_text()
    assert "weather" in tools_py
    assert "calculator" in tools_py


def test_scaffold_creates_tests(tmp_path: Path):
    project = scaffold_project("test-server", output_dir=tmp_path)
    assert (project / "tests" / "test_test_server.py").exists()


def test_scaffold_creates_gitignore(tmp_path: Path):
    project = scaffold_project("test-server", output_dir=tmp_path)
    assert (project / ".gitignore").exists()
