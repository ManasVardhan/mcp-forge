"""Tests for template publishing: build_template_from_project and publish_template."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from mcp_forge.cli import cli
from mcp_forge.marketplace import (
    MarketplaceError,
    Template,
    build_template_from_project,
    get_template,
    install_template,
    load_registry,
    publish_template,
)
from mcp_forge.scaffold import scaffold_project


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A scaffolded project with tools, a resource, and a prompt."""
    return scaffold_project(
        name="weather-api",
        output_dir=tmp_path,
        tools=["get_forecast", "get_alerts"],
        resources=["config://settings"],
        prompts=["summarize"],
        description="Weather MCP server.",
        author="Casey Dev",
    )


class TestBuildTemplateFromProject:
    def test_scans_capabilities(self, project):
        template = build_template_from_project(project)
        assert template.name == "weather-api"
        assert template.tools == ["get_forecast", "get_alerts"]
        assert template.resources == ["config://settings"]
        assert template.prompts == ["summarize"]

    def test_reads_pyproject_metadata(self, project):
        template = build_template_from_project(project)
        assert template.version == "0.1.0"
        assert template.description == "Weather MCP server."
        assert template.author == "Casey Dev"

    def test_name_override(self, project):
        template = build_template_from_project(project, name="wx")
        assert template.name == "wx"

    def test_tools_only_project(self, tmp_path):
        root = scaffold_project(name="tools-only", output_dir=tmp_path, tools=["ping"])
        template = build_template_from_project(root)
        assert template.tools == ["ping"]
        assert template.resources == []
        assert template.prompts == []

    def test_include_embeds_with_placeholders(self, project):
        notes = project / "NOTES.md"
        notes.write_text(
            "# weather-api notes\nimport weather_api\n", encoding="utf-8"
        )
        template = build_template_from_project(project, include=["NOTES.md"])
        content = template.extra_files["NOTES.md"]
        assert "{{project_name}}" in content
        assert "{{pkg_name}}" in content
        assert "weather-api" not in content
        assert "weather_api" not in content

    def test_include_nested_path(self, project):
        docs = project / "docs"
        docs.mkdir()
        (docs / "usage.md").write_text("Use weather-api daily.", encoding="utf-8")
        template = build_template_from_project(project, include=["docs/usage.md"])
        assert "docs/usage.md" in template.extra_files

    def test_missing_pyproject(self, tmp_path):
        empty = tmp_path / "not-a-project"
        empty.mkdir()
        with pytest.raises(MarketplaceError, match="No pyproject.toml"):
            build_template_from_project(empty)

    def test_include_missing_file(self, project):
        with pytest.raises(MarketplaceError, match="does not exist"):
            build_template_from_project(project, include=["ghost.md"])

    def test_include_escape_rejected(self, project):
        with pytest.raises(MarketplaceError, match="stay inside the project"):
            build_template_from_project(project, include=["../outside.md"])

    def test_include_binary_rejected(self, project):
        blob = project / "logo.bin"
        blob.write_bytes(b"\xff\xfe\x00binary")
        with pytest.raises(MarketplaceError, match="not UTF-8"):
            build_template_from_project(project, include=["logo.bin"])


class TestPublishTemplate:
    def test_creates_registry(self, tmp_path):
        registry = tmp_path / "registry.json"
        template = Template(name="fresh", tools=["go"])
        written = publish_template(template, registry)
        assert written == registry
        data = json.loads(registry.read_text())
        assert data["registry_version"] == 1
        assert data["templates"][0]["name"] == "fresh"

    def test_preserves_existing_entries(self, tmp_path):
        registry = tmp_path / "registry.json"
        publish_template(Template(name="first"), registry)
        publish_template(Template(name="second"), registry)
        names = [t.name for t in load_registry(str(registry))]
        assert names == ["first", "second"]

    def test_duplicate_without_force(self, tmp_path):
        registry = tmp_path / "registry.json"
        publish_template(Template(name="dup", version="1.0.0"), registry)
        with pytest.raises(MarketplaceError, match="already exists"):
            publish_template(Template(name="dup", version="2.0.0"), registry)

    def test_force_replaces(self, tmp_path):
        registry = tmp_path / "registry.json"
        publish_template(Template(name="dup", version="1.0.0"), registry)
        publish_template(Template(name="dup", version="2.0.0"), registry, force=True)
        templates = load_registry(str(registry))
        assert len(templates) == 1
        assert templates[0].version == "2.0.0"

    def test_malformed_existing_registry(self, tmp_path):
        registry = tmp_path / "registry.json"
        registry.write_text("{broken")
        with pytest.raises(MarketplaceError, match="not valid JSON"):
            publish_template(Template(name="x"), registry)

    def test_creates_parent_dirs(self, tmp_path):
        registry = tmp_path / "deep" / "nested" / "registry.json"
        publish_template(Template(name="x"), registry)
        assert registry.is_file()


class TestPublishInstallRoundTrip:
    def test_published_template_installs(self, project, tmp_path):
        (project / "NOTES.md").write_text(
            "# weather-api\npkg weather_api\n", encoding="utf-8"
        )
        template = build_template_from_project(project, include=["NOTES.md"])
        registry = tmp_path / "registry.json"
        publish_template(template, registry)

        out_dir = tmp_path / "installs"
        out_dir.mkdir()
        new_root = install_template(
            "weather-api",
            project_name="storm-watch",
            source=str(registry),
            output_dir=out_dir,
        )
        assert (new_root / "src" / "storm_watch" / "tools.py").is_file()
        notes = (new_root / "NOTES.md").read_text(encoding="utf-8")
        assert "storm-watch" in notes
        assert "storm_watch" in notes
        assert "{{" not in notes

        installed = get_template("weather-api", str(registry))
        assert installed.tools == ["get_forecast", "get_alerts"]


class TestPublishCLI:
    def test_publish_success(self, project, tmp_path):
        registry = tmp_path / "registry.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["template", "publish", str(project), "-r", str(registry)],
        )
        assert result.exit_code == 0
        assert "Published" in result.output
        assert "weather-api" in result.output
        assert registry.is_file()

    def test_publish_json_output(self, project, tmp_path):
        registry = tmp_path / "registry.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["template", "publish", str(project), "-r", str(registry), "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["name"] == "weather-api"
        assert payload["tools"] == ["get_forecast", "get_alerts"]

    def test_publish_with_name_and_include(self, project, tmp_path):
        (project / "NOTES.md").write_text("weather-api notes", encoding="utf-8")
        registry = tmp_path / "registry.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "template", "publish", str(project),
                "-r", str(registry),
                "-n", "wx-starter",
                "-i", "NOTES.md",
            ],
        )
        assert result.exit_code == 0
        template = get_template("wx-starter", str(registry))
        assert "NOTES.md" in template.extra_files

    def test_publish_duplicate_errors(self, project, tmp_path):
        registry = tmp_path / "registry.json"
        runner = CliRunner()
        first = runner.invoke(
            cli, ["template", "publish", str(project), "-r", str(registry)]
        )
        assert first.exit_code == 0
        second = runner.invoke(
            cli, ["template", "publish", str(project), "-r", str(registry)]
        )
        assert second.exit_code == 1
        assert "already exists" in second.output

    def test_publish_force_overwrites(self, project, tmp_path):
        registry = tmp_path / "registry.json"
        runner = CliRunner()
        runner.invoke(cli, ["template", "publish", str(project), "-r", str(registry)])
        result = runner.invoke(
            cli,
            ["template", "publish", str(project), "-r", str(registry), "--force"],
        )
        assert result.exit_code == 0

    def test_publish_not_a_project(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        registry = tmp_path / "registry.json"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["template", "publish", str(empty), "-r", str(registry)]
        )
        assert result.exit_code == 1
        assert "No pyproject.toml" in result.output
