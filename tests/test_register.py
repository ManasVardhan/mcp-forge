"""Tests for the `mcp-forge register` command.

Covers adding, overwriting, and removing Claude Desktop config entries,
config preservation, error handling, and default path selection.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from mcp_forge.cli import _default_claude_config_path, cli


def _make_project(tmp_path: Path, name: str = "weather-server") -> Path:
    project = tmp_path / name
    project.mkdir()
    (project / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
    )
    return project


class TestRegisterAdd:
    def test_creates_config_and_entry(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "claude" / "claude_desktop_config.json"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config)]
        )
        assert result.exit_code == 0
        data = json.loads(config.read_text())
        entry = data["mcpServers"]["weather-server"]
        assert entry["command"] == "python"
        assert entry["args"] == ["-m", "weather_server.server"]

    def test_default_cmd_converts_hyphens(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path, name="my-cool-server")
        config = tmp_path / "cfg.json"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config)]
        )
        assert result.exit_code == 0
        entry = json.loads(config.read_text())["mcpServers"]["my-cool-server"]
        assert entry["args"] == ["-m", "my_cool_server.server"]

    def test_explicit_name_and_cmd(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "register", str(project),
            "--config", str(config),
            "--name", "custom",
            "--cmd", "uv run server.py --port 8080",
        ])
        assert result.exit_code == 0
        entry = json.loads(config.read_text())["mcpServers"]["custom"]
        assert entry["command"] == "uv"
        assert entry["args"] == ["run", "server.py", "--port", "8080"]

    def test_name_from_directory_without_pyproject(self, tmp_path: Path) -> None:
        project = tmp_path / "bare-server"
        project.mkdir()
        config = tmp_path / "cfg.json"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config)]
        )
        assert result.exit_code == 0
        assert "bare-server" in json.loads(config.read_text())["mcpServers"]

    def test_preserves_existing_config(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        config.write_text(json.dumps({
            "globalShortcut": "Ctrl+Space",
            "mcpServers": {"other": {"command": "node", "args": ["x.js"]}},
        }))
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config)]
        )
        assert result.exit_code == 0
        data = json.loads(config.read_text())
        assert data["globalShortcut"] == "Ctrl+Space"
        assert data["mcpServers"]["other"]["command"] == "node"
        assert "weather-server" in data["mcpServers"]

    def test_existing_entry_requires_force(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        config.write_text(json.dumps({
            "mcpServers": {"weather-server": {"command": "old", "args": []}},
        }))
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config)]
        )
        assert result.exit_code == 1
        assert "already exists" in result.output
        # Original entry untouched
        data = json.loads(config.read_text())
        assert data["mcpServers"]["weather-server"]["command"] == "old"

    def test_force_overwrites(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        config.write_text(json.dumps({
            "mcpServers": {"weather-server": {"command": "old", "args": []}},
        }))
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config), "--force"]
        )
        assert result.exit_code == 0
        data = json.loads(config.read_text())
        assert data["mcpServers"]["weather-server"]["command"] == "python"

    def test_output_mentions_restart(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config)]
        )
        assert "Restart Claude Desktop" in result.output

    def test_written_file_is_valid_json_with_newline(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        runner = CliRunner()
        runner.invoke(cli, ["register", str(project), "--config", str(config)])
        text = config.read_text()
        assert text.endswith("\n")
        json.loads(text)


class TestRegisterRemove:
    def test_remove_entry(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        config.write_text(json.dumps({
            "mcpServers": {
                "weather-server": {"command": "python", "args": []},
                "other": {"command": "node", "args": []},
            },
        }))
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config), "--remove"]
        )
        assert result.exit_code == 0
        data = json.loads(config.read_text())
        assert "weather-server" not in data["mcpServers"]
        assert "other" in data["mcpServers"]

    def test_remove_missing_entry_fails(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        config.write_text(json.dumps({"mcpServers": {}}))
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config), "--remove"]
        )
        assert result.exit_code == 1
        assert "No entry" in result.output


class TestRegisterDryRun:
    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config), "--dry-run"]
        )
        assert result.exit_code == 0
        assert not config.exists()
        assert "weather_server.server" in result.output

    def test_dry_run_leaves_existing_file_untouched(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        original = json.dumps({"mcpServers": {}})
        config.write_text(original)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config), "--dry-run"]
        )
        assert result.exit_code == 0
        assert config.read_text() == original


class TestRegisterErrors:
    def test_invalid_json_config(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        config.write_text("{not valid json")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config)]
        )
        assert result.exit_code == 1
        assert "Could not parse" in result.output
        # File untouched
        assert config.read_text() == "{not valid json"

    def test_non_object_config(self, tmp_path: Path) -> None:
        project = _make_project(tmp_path)
        config = tmp_path / "cfg.json"
        config.write_text("[1, 2, 3]")
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(project), "--config", str(config)]
        )
        assert result.exit_code == 1
        assert "JSON object" in result.output

    def test_missing_project_dir(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["register", str(tmp_path / "nope")]
        )
        assert result.exit_code != 0


class TestDefaultConfigPath:
    def test_darwin_path(self, monkeypatch) -> None:
        monkeypatch.setattr("sys.platform", "darwin")
        path = _default_claude_config_path()
        assert "Application Support" in str(path)
        assert path.name == "claude_desktop_config.json"

    def test_linux_path(self, monkeypatch) -> None:
        monkeypatch.setattr("sys.platform", "linux")
        path = _default_claude_config_path()
        assert ".config" in str(path)
        assert path.name == "claude_desktop_config.json"

    def test_win32_path(self, monkeypatch) -> None:
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("APPDATA", "C:/Users/test/AppData/Roaming")
        path = _default_claude_config_path()
        assert "Claude" in str(path)
        assert path.name == "claude_desktop_config.json"
