"""Tests for the hot reload dev server."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from mcp_forge.cli import cli
from mcp_forge.devserver import (
    DEFAULT_EXTENSIONS,
    DevServer,
    FileChanges,
    diff_snapshots,
    snapshot_files,
)

SLEEP_CMD = [sys.executable, "-c", "import time; time.sleep(60)"]
EXIT_CMD = [sys.executable, "-c", "pass"]


# ---------------------------------------------------------------------------
# snapshot_files
# ---------------------------------------------------------------------------


class TestSnapshotFiles:
    def test_collects_watched_files(self, tmp_path: Path) -> None:
        (tmp_path / "server.py").write_text("print('hi')")
        (tmp_path / "pyproject.toml").write_text("[project]")
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "tools.py").write_text("x = 1")

        snap = snapshot_files(tmp_path)

        assert set(snap) == {
            tmp_path / "server.py",
            tmp_path / "pyproject.toml",
            sub / "tools.py",
        }

    def test_ignores_unwatched_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("notes")
        (tmp_path / "server.py").write_text("x = 1")

        snap = snapshot_files(tmp_path)

        assert list(snap) == [tmp_path / "server.py"]

    def test_ignores_pycache_and_hidden_dirs(self, tmp_path: Path) -> None:
        for dirname in ("__pycache__", ".git", ".venv", "node_modules", "dist"):
            d = tmp_path / dirname
            d.mkdir()
            (d / "ignored.py").write_text("x = 1")
        egg = tmp_path / "pkg.egg-info"
        egg.mkdir()
        (egg / "meta.json").write_text("{}")
        (tmp_path / "kept.py").write_text("x = 1")

        snap = snapshot_files(tmp_path)

        assert list(snap) == [tmp_path / "kept.py"]

    def test_custom_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "config.yaml").write_text("a: 1")
        (tmp_path / "server.py").write_text("x = 1")

        snap = snapshot_files(tmp_path, extensions=(".yaml",))

        assert list(snap) == [tmp_path / "config.yaml"]

    def test_empty_directory(self, tmp_path: Path) -> None:
        assert snapshot_files(tmp_path) == {}


# ---------------------------------------------------------------------------
# diff_snapshots / FileChanges
# ---------------------------------------------------------------------------


class TestDiffSnapshots:
    def test_no_changes(self, tmp_path: Path) -> None:
        snap = {tmp_path / "a.py": 1.0}
        changes = diff_snapshots(snap, dict(snap))
        assert not changes.has_changes

    def test_added_modified_deleted(self, tmp_path: Path) -> None:
        a, b, c = tmp_path / "a.py", tmp_path / "b.py", tmp_path / "c.py"
        before = {a: 1.0, b: 1.0}
        after = {a: 2.0, c: 1.0}

        changes = diff_snapshots(before, after)

        assert changes.modified == [a]
        assert changes.added == [c]
        assert changes.deleted == [b]
        assert changes.has_changes

    def test_describe_lists_names(self, tmp_path: Path) -> None:
        changes = FileChanges(
            added=[tmp_path / "new.py"],
            modified=[tmp_path / "srv.py"],
            deleted=[tmp_path / "old.py"],
        )
        text = changes.describe()
        assert "added: new.py" in text
        assert "modified: srv.py" in text
        assert "deleted: old.py" in text

    def test_describe_caps_at_three_names(self, tmp_path: Path) -> None:
        changes = FileChanges(modified=[tmp_path / f"f{i}.py" for i in range(5)])
        text = changes.describe()
        assert "(+2 more)" in text
        assert text.count(".py") == 3

    def test_describe_empty(self) -> None:
        assert FileChanges().describe() == ""


# ---------------------------------------------------------------------------
# DevServer
# ---------------------------------------------------------------------------


class TestDevServerValidation:
    def test_empty_command_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="server_cmd"):
            DevServer([], tmp_path)

    def test_nonpositive_interval_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="interval"):
            DevServer(SLEEP_CMD, tmp_path, interval=0)
        with pytest.raises(ValueError, match="interval"):
            DevServer(SLEEP_CMD, tmp_path, interval=-1)

    def test_missing_watch_dir_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="watch directory"):
            DevServer(SLEEP_CMD, tmp_path / "nope")

    def test_empty_extensions_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="extensions"):
            DevServer(SLEEP_CMD, tmp_path, extensions=())


class TestDevServerLifecycle:
    def test_start_and_stop(self, tmp_path: Path) -> None:
        server = DevServer(SLEEP_CMD, tmp_path)
        server.start()
        try:
            assert server.is_running
        finally:
            server.stop()
        assert not server.is_running

    def test_stop_without_start_is_noop(self, tmp_path: Path) -> None:
        server = DevServer(SLEEP_CMD, tmp_path)
        server.stop()
        assert not server.is_running

    def test_poll_without_changes_does_not_restart(self, tmp_path: Path) -> None:
        (tmp_path / "server.py").write_text("x = 1")
        server = DevServer(SLEEP_CMD, tmp_path)
        server.start()
        try:
            assert server.poll_once() is False
            assert server.restart_count == 0
        finally:
            server.stop()

    def test_restart_on_added_file(self, tmp_path: Path) -> None:
        (tmp_path / "server.py").write_text("x = 1")
        server = DevServer(SLEEP_CMD, tmp_path)
        server.start()
        try:
            (tmp_path / "extra.py").write_text("y = 2")
            assert server.poll_once() is True
            assert server.restart_count == 1
            assert server.is_running
        finally:
            server.stop()

    def test_restart_on_modified_file(self, tmp_path: Path) -> None:
        target = tmp_path / "server.py"
        target.write_text("x = 1")
        server = DevServer(SLEEP_CMD, tmp_path)
        server.start()
        try:
            target.write_text("x = 2")
            os.utime(target, (time.time() + 10, time.time() + 10))
            assert server.poll_once() is True
            assert server.restart_count == 1
        finally:
            server.stop()

    def test_restart_on_deleted_file(self, tmp_path: Path) -> None:
        target = tmp_path / "server.py"
        target.write_text("x = 1")
        server = DevServer(SLEEP_CMD, tmp_path)
        server.start()
        try:
            target.unlink()
            assert server.poll_once() is True
            assert server.restart_count == 1
        finally:
            server.stop()

    def test_revives_dead_server(self, tmp_path: Path) -> None:
        server = DevServer(EXIT_CMD, tmp_path)
        server.start()
        try:
            assert server._process is not None
            server._process.wait(timeout=10)
            assert server.poll_once() is True
            assert server.restart_count == 1
            assert not server.gave_up
        finally:
            server.stop()

    def test_gives_up_after_crash_loop(self, tmp_path: Path) -> None:
        server = DevServer(EXIT_CMD, tmp_path, max_crashes=3)
        server.start()
        try:
            restarts = 0
            for _ in range(10):
                assert server._process is not None
                server._process.wait(timeout=10)
                if not server.poll_once():
                    break
                restarts += 1
            assert server.gave_up
            assert restarts == 2
        finally:
            server.stop()

    def test_healthy_tick_resets_crash_counter(self, tmp_path: Path) -> None:
        server = DevServer(SLEEP_CMD, tmp_path, max_crashes=2)
        server.start()
        try:
            assert server._process is not None
            server._process.terminate()
            server._process.wait(timeout=10)
            assert server.poll_once() is True  # one crash, revived
            assert server.poll_once() is False  # healthy tick resets counter
            assert server._consecutive_crashes == 0
            assert not server.gave_up
        finally:
            server.stop()

    def test_run_stops_when_giving_up(self, tmp_path: Path) -> None:
        server = DevServer(EXIT_CMD, tmp_path, interval=0.05, max_crashes=2)
        server.run(max_iterations=50)
        assert server.gave_up
        assert not server.is_running

    def test_invalid_max_crashes_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="max_crashes"):
            DevServer(SLEEP_CMD, tmp_path, max_crashes=0)

    def test_run_bounded_iterations(self, tmp_path: Path) -> None:
        (tmp_path / "server.py").write_text("x = 1")
        server = DevServer(SLEEP_CMD, tmp_path, interval=0.05)
        server.run(max_iterations=2)
        assert server.restart_count == 0
        assert not server.is_running

    def test_run_restarts_on_change(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "server.py").write_text("x = 1")
        server = DevServer(SLEEP_CMD, tmp_path, interval=0.05)

        def sleep_and_touch(_seconds: float) -> None:
            (tmp_path / "new.py").write_text("y = 2")

        monkeypatch.setattr("mcp_forge.devserver.time.sleep", sleep_and_touch)
        server.run(max_iterations=1)
        assert server.restart_count == 1
        assert not server.is_running


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _FakeDevServer:
    """Captures constructor args and records run() calls."""

    instances: list["_FakeDevServer"] = []

    def __init__(self, server_cmd, watch_dir, **kwargs):
        self.server_cmd = server_cmd
        self.watch_dir = watch_dir
        self.kwargs = kwargs
        self.ran = False
        self.gave_up = False
        _FakeDevServer.instances.append(self)

    def run(self, max_iterations=None):
        self.ran = True


class _GivingUpDevServer(_FakeDevServer):
    def run(self, max_iterations=None):
        super().run(max_iterations)
        self.gave_up = True


@pytest.fixture(autouse=True)
def _clear_fake_instances():
    _FakeDevServer.instances = []
    yield
    _FakeDevServer.instances = []


class TestDevCommand:
    def test_help(self) -> None:
        result = CliRunner().invoke(cli, ["dev", "--help"])
        assert result.exit_code == 0
        assert "hot reload" in result.output.lower()

    def test_invalid_interval_exits(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(cli, ["dev", str(tmp_path), "--interval", "0"])
        assert result.exit_code == 1
        assert "interval" in result.output

    def test_default_cmd_from_pyproject(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-server"\n')
        monkeypatch.setattr("mcp_forge.cli.DevServer", _FakeDevServer)

        result = CliRunner().invoke(cli, ["dev", str(tmp_path)])

        assert result.exit_code == 0
        fake = _FakeDevServer.instances[0]
        assert fake.server_cmd == [sys.executable, "-m", "my_server.server"]
        assert fake.ran

    def test_default_cmd_from_dirname_without_pyproject(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        project = tmp_path / "cool-proj"
        project.mkdir()
        monkeypatch.setattr("mcp_forge.cli.DevServer", _FakeDevServer)

        result = CliRunner().invoke(cli, ["dev", str(project)])

        assert result.exit_code == 0
        fake = _FakeDevServer.instances[0]
        assert fake.server_cmd == [sys.executable, "-m", "cool_proj.server"]

    def test_explicit_cmd_is_split(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("mcp_forge.cli.DevServer", _FakeDevServer)

        result = CliRunner().invoke(
            cli, ["dev", str(tmp_path), "--cmd", "uv run server.py"]
        )

        assert result.exit_code == 0
        fake = _FakeDevServer.instances[0]
        assert fake.server_cmd == ["uv", "run", "server.py"]

    def test_custom_extensions_normalized(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("mcp_forge.cli.DevServer", _FakeDevServer)

        result = CliRunner().invoke(
            cli, ["dev", str(tmp_path), "--ext", "py, yaml,.json"]
        )

        assert result.exit_code == 0
        fake = _FakeDevServer.instances[0]
        assert fake.kwargs["extensions"] == (".py", ".yaml", ".json")

    def test_default_extensions_used(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("mcp_forge.cli.DevServer", _FakeDevServer)

        result = CliRunner().invoke(cli, ["dev", str(tmp_path)])

        assert result.exit_code == 0
        fake = _FakeDevServer.instances[0]
        assert fake.kwargs["extensions"] == DEFAULT_EXTENSIONS

    def test_exit_code_1_when_giving_up(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("mcp_forge.cli.DevServer", _GivingUpDevServer)

        result = CliRunner().invoke(cli, ["dev", str(tmp_path)])

        assert result.exit_code == 1


class TestMissingExecutable:
    def test_run_with_missing_executable_gives_up_cleanly(self, tmp_path: Path) -> None:
        server = DevServer(["definitely-not-a-real-binary-xyz"], tmp_path, interval=0.05)
        server.run(max_iterations=1)
        assert server.gave_up
        assert not server.is_running
