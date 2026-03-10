"""Extended tests for the scaffold module."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_forge.scaffold import get_template_env, scaffold_project, snake_case, title_case


class TestSnakeCase:
    def test_hyphenated(self) -> None:
        assert snake_case("my-cool-server") == "my_cool_server"

    def test_spaces(self) -> None:
        assert snake_case("My Cool Server") == "my_cool_server"

    def test_already_snake(self) -> None:
        assert snake_case("my_server") == "my_server"

    def test_mixed(self) -> None:
        assert snake_case("my-cool server") == "my_cool_server"

    def test_single_word(self) -> None:
        assert snake_case("server") == "server"

    def test_uppercase(self) -> None:
        assert snake_case("MY-SERVER") == "my_server"


class TestTitleCase:
    def test_hyphenated(self) -> None:
        assert title_case("my-server") == "My Server"

    def test_underscored(self) -> None:
        assert title_case("my_server") == "My Server"

    def test_single_word(self) -> None:
        assert title_case("server") == "Server"


class TestGetTemplateEnv:
    def test_env_loads(self) -> None:
        env = get_template_env()
        assert env is not None

    def test_env_has_templates(self) -> None:
        env = get_template_env()
        # Should be able to load known templates
        template = env.get_template("server.py.j2")
        assert template is not None


class TestScaffoldProject:
    def test_default_output_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        project = scaffold_project("test-server")
        assert project.exists()
        assert project == tmp_path / "test-server"

    def test_custom_output_dir(self, tmp_path: Path) -> None:
        project = scaffold_project("test-server", output_dir=tmp_path)
        assert project == tmp_path / "test-server"

    def test_creates_all_expected_files(self, tmp_path: Path) -> None:
        project = scaffold_project("test-server", output_dir=tmp_path)
        pkg = project / "src" / "test_server"
        assert (pkg / "__init__.py").exists()
        assert (pkg / "server.py").exists()
        assert (pkg / "tools.py").exists()
        assert (pkg / "resources.py").exists()
        assert (project / "pyproject.toml").exists()
        assert (project / "README.md").exists()
        assert (project / "Dockerfile").exists()
        assert (project / ".gitignore").exists()
        assert (project / "tests" / "test_test_server.py").exists()

    def test_default_tool_is_hello(self, tmp_path: Path) -> None:
        project = scaffold_project("test-server", output_dir=tmp_path)
        tools_content = (project / "src" / "test_server" / "tools.py").read_text()
        assert "hello" in tools_content

    def test_custom_tools(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "test-server", output_dir=tmp_path, tools=["weather", "calculator"]
        )
        tools_content = (project / "src" / "test_server" / "tools.py").read_text()
        assert "weather" in tools_content
        assert "calculator" in tools_content

    def test_custom_resources(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "test-server", output_dir=tmp_path, resources=["file://data"]
        )
        resources_content = (project / "src" / "test_server" / "resources.py").read_text()
        assert "file://data" in resources_content

    def test_custom_description(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "test-server", output_dir=tmp_path, description="My awesome server"
        )
        readme = (project / "README.md").read_text()
        assert "My awesome server" in readme

    def test_custom_author(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "test-server", output_dir=tmp_path, author="Alice"
        )
        pyproject = (project / "pyproject.toml").read_text()
        assert "Alice" in pyproject

    def test_default_author(self, tmp_path: Path) -> None:
        project = scaffold_project("test-server", output_dir=tmp_path)
        pyproject = (project / "pyproject.toml").read_text()
        assert "Author" in pyproject

    def test_gitignore_contents(self, tmp_path: Path) -> None:
        project = scaffold_project("test-server", output_dir=tmp_path)
        gitignore = (project / ".gitignore").read_text()
        assert "__pycache__" in gitignore
        assert ".venv" in gitignore

    def test_test_file_contents(self, tmp_path: Path) -> None:
        project = scaffold_project("test-server", output_dir=tmp_path)
        test_file = (project / "tests" / "test_test_server.py").read_text()
        assert "test_import" in test_file
        assert "test_server_module" in test_file
        assert "test_server" in test_file  # pkg name

    def test_server_has_mcp_instance(self, tmp_path: Path) -> None:
        project = scaffold_project("test-server", output_dir=tmp_path)
        server_content = (project / "src" / "test_server" / "server.py").read_text()
        assert "mcp = MCPServer()" in server_content

    def test_dockerfile_content(self, tmp_path: Path) -> None:
        project = scaffold_project("test-server", output_dir=tmp_path)
        dockerfile = (project / "Dockerfile").read_text()
        assert "FROM python" in dockerfile
        assert "pip install" in dockerfile

    def test_idempotent_scaffold(self, tmp_path: Path) -> None:
        """Scaffolding same project twice should not raise."""
        scaffold_project("test-server", output_dir=tmp_path)
        # Second call should overwrite without error
        project = scaffold_project("test-server", output_dir=tmp_path)
        assert project.exists()
