"""Tests for the template marketplace."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from click.testing import CliRunner

from mcp_forge.cli import cli
from mcp_forge.marketplace import (
    MarketplaceError,
    Template,
    get_template,
    install_template,
    load_registry,
)


def make_registry(tmp_path: Path, templates: list[dict]) -> str:
    path = tmp_path / "registry.json"
    path.write_text(json.dumps({"registry_version": 1, "templates": templates}))
    return str(path)


SIMPLE_TEMPLATE = {
    "name": "simple",
    "version": "2.1.0",
    "description": "A simple test template.",
    "author": "Tester",
    "tools": ["greet"],
    "resources": ["config://app"],
    "prompts": ["welcome"],
    "extra_files": {"NOTES.md": "# {{project_name}}\npkg: {{pkg_name}}\n"},
}


class TestLoadRegistry:
    def test_builtin_registry_loads(self):
        templates = load_registry()
        names = [t.name for t in templates]
        assert "starter" in names
        assert "api-client" in names
        assert "knowledge-base" in names

    def test_local_registry(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        templates = load_registry(source)
        assert len(templates) == 1
        assert templates[0].name == "simple"
        assert templates[0].version == "2.1.0"
        assert templates[0].tools == ["greet"]

    def test_missing_file(self, tmp_path):
        with pytest.raises(MarketplaceError, match="not found"):
            load_registry(str(tmp_path / "nope.json"))

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json")
        with pytest.raises(MarketplaceError, match="not valid JSON"):
            load_registry(str(path))

    def test_wrong_shape(self, tmp_path):
        path = tmp_path / "shape.json"
        path.write_text(json.dumps({"templates": "nope"}))
        with pytest.raises(MarketplaceError, match="'templates' list"):
            load_registry(str(path))

    def test_unsupported_version(self, tmp_path):
        path = tmp_path / "v99.json"
        path.write_text(json.dumps({"registry_version": 99, "templates": []}))
        with pytest.raises(MarketplaceError, match="unsupported registry_version"):
            load_registry(str(path))

    def test_duplicate_names(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE, SIMPLE_TEMPLATE])
        with pytest.raises(MarketplaceError, match="duplicate"):
            load_registry(source)

    def test_missing_name(self, tmp_path):
        source = make_registry(tmp_path, [{"version": "1.0.0"}])
        with pytest.raises(MarketplaceError, match="missing a 'name'"):
            load_registry(source)

    def test_bad_tools_type(self, tmp_path):
        source = make_registry(tmp_path, [{"name": "x", "tools": "greet"}])
        with pytest.raises(MarketplaceError, match="list of strings"):
            load_registry(source)

    def test_bad_extra_files_type(self, tmp_path):
        source = make_registry(tmp_path, [{"name": "x", "extra_files": {"a": 1}}])
        with pytest.raises(MarketplaceError, match="extra_files"):
            load_registry(source)

    def test_http_registry(self, tmp_path):
        payload = json.dumps(
            {"registry_version": 1, "templates": [SIMPLE_TEMPLATE]}
        ).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/registry.json"
            templates = load_registry(url)
            assert templates[0].name == "simple"
        finally:
            server.shutdown()

    def test_http_registry_unreachable(self):
        with pytest.raises(MarketplaceError, match="Could not fetch"):
            load_registry("http://127.0.0.1:1/registry.json")


class TestGetTemplate:
    def test_found(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        assert get_template("simple", source).description == "A simple test template."

    def test_not_found_lists_available(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        with pytest.raises(MarketplaceError, match="Available: simple"):
            get_template("nope", source)


class TestInstallTemplate:
    def test_install_scaffolds_capabilities(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        root = install_template(
            "simple", project_name="my-app", source=source, output_dir=tmp_path
        )
        assert root == tmp_path / "my-app"
        tools_py = (root / "src" / "my_app" / "tools.py").read_text()
        assert "greet" in tools_py
        assert "welcome" in (root / "src" / "my_app" / "prompts.py").read_text()
        assert "config://app" in (root / "src" / "my_app" / "resources.py").read_text()

    def test_install_writes_extra_files_with_placeholders(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        root = install_template(
            "simple", project_name="my-app", source=source, output_dir=tmp_path
        )
        notes = (root / "NOTES.md").read_text()
        assert "# my-app" in notes
        assert "pkg: my_app" in notes

    def test_install_defaults_project_name_to_template(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        root = install_template("simple", source=source, output_dir=tmp_path)
        assert root.name == "simple"

    def test_install_uses_template_description_and_author(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        root = install_template("simple", source=source, output_dir=tmp_path)
        pyproject = (root / "pyproject.toml").read_text()
        assert "A simple test template." in pyproject
        assert "Tester" in pyproject

    def test_install_rejects_invalid_project_name(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        with pytest.raises(ValueError):
            install_template(
                "simple", project_name="1bad", source=source, output_dir=tmp_path
            )

    @pytest.mark.parametrize("path", ["../escape.md", "/tmp/abs.md", "a/../../b.md"])
    def test_install_rejects_escaping_extra_files(self, tmp_path, path):
        bad = dict(SIMPLE_TEMPLATE)
        bad["extra_files"] = {path: "nope"}
        source = make_registry(tmp_path, [bad])
        with pytest.raises(MarketplaceError, match="must be relative|escapes"):
            install_template(
                "simple", project_name="my-app", source=source, output_dir=tmp_path
            )

    def test_install_nested_extra_file(self, tmp_path):
        nested = dict(SIMPLE_TEMPLATE)
        nested["extra_files"] = {"docs/guide.md": "hello {{project_name}}"}
        source = make_registry(tmp_path, [nested])
        root = install_template(
            "simple", project_name="my-app", source=source, output_dir=tmp_path
        )
        assert (root / "docs" / "guide.md").read_text() == "hello my-app"

    def test_builtin_templates_install_and_generate_valid_python(self, tmp_path):
        import ast

        for template in load_registry():
            root = install_template(template.name, output_dir=tmp_path)
            for py_file in root.rglob("*.py"):
                ast.parse(py_file.read_text())


class TestTemplateCli:
    def test_list_builtin(self):
        result = CliRunner().invoke(cli, ["template", "list"])
        assert result.exit_code == 0
        assert "starter" in result.output
        assert "api-client" in result.output

    def test_list_json(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        result = CliRunner().invoke(
            cli, ["template", "list", "--registry", source, "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "simple"

    def test_list_bad_registry(self, tmp_path):
        result = CliRunner().invoke(
            cli, ["template", "list", "--registry", str(tmp_path / "nope.json")]
        )
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_show(self):
        result = CliRunner().invoke(cli, ["template", "show", "knowledge-base"])
        assert result.exit_code == 0
        assert "summarize_doc" in result.output
        assert "docs://index" in result.output

    def test_show_json(self):
        result = CliRunner().invoke(cli, ["template", "show", "starter", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["name"] == "starter"

    def test_show_unknown(self):
        result = CliRunner().invoke(cli, ["template", "show", "nope"])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_install(self, tmp_path):
        source = make_registry(tmp_path, [SIMPLE_TEMPLATE])
        result = CliRunner().invoke(
            cli,
            [
                "template", "install", "simple", "cli-app",
                "--registry", source, "--output-dir", str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "Project created" in result.output
        assert (tmp_path / "cli-app" / "NOTES.md").exists()

    def test_install_unknown(self, tmp_path):
        result = CliRunner().invoke(
            cli, ["template", "install", "nope", "--output-dir", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "not found" in result.output


class TestTemplateDataclass:
    def test_round_trip(self):
        t = Template.from_dict(SIMPLE_TEMPLATE)
        assert t.to_dict() == SIMPLE_TEMPLATE

    def test_defaults(self):
        t = Template.from_dict({"name": "bare"})
        assert t.version == "1.0.0"
        assert t.tools == []
        assert t.extra_files == {}
