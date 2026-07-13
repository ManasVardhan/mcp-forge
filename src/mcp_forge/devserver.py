"""Hot reload development server: watch project files and restart the MCP server.

The watcher is a simple polling loop with no extra dependencies. It snapshots
modification times for watched files, diffs snapshots on every tick, and
restarts the server subprocess whenever something was added, modified, or
deleted. It also revives the server if it crashes or exits on its own.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

DEFAULT_EXTENSIONS: tuple[str, ...] = (".py", ".toml", ".json", ".j2")

IGNORED_DIRS: frozenset[str] = frozenset({
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "venv",
})


def _is_ignored(path: Path, root: Path) -> bool:
    """Return True if any directory between root and path should be skipped."""
    relative = path.relative_to(root)
    for part in relative.parts[:-1]:
        if part in IGNORED_DIRS or part.startswith(".") or part.endswith(".egg-info"):
            return True
    return False


def snapshot_files(
    root: Path, extensions: tuple[str, ...] = DEFAULT_EXTENSIONS
) -> dict[Path, float]:
    """Map watched files under root to their modification times.

    Files inside hidden directories, __pycache__, virtualenvs, and build
    output are skipped, as are files whose suffix is not being watched.
    """
    snapshot: dict[Path, float] = {}
    for path in root.rglob("*"):
        if path.suffix not in extensions or not path.is_file():
            continue
        if _is_ignored(path, root):
            continue
        try:
            snapshot[path] = path.stat().st_mtime
        except OSError:
            continue
    return snapshot


@dataclass
class FileChanges:
    """Difference between two file snapshots."""

    added: list[Path] = field(default_factory=list)
    modified: list[Path] = field(default_factory=list)
    deleted: list[Path] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    def describe(self) -> str:
        """Short human-readable summary, capped at 3 names per category."""
        parts: list[str] = []
        for label, paths in (
            ("added", self.added),
            ("modified", self.modified),
            ("deleted", self.deleted),
        ):
            if not paths:
                continue
            names = ", ".join(p.name for p in sorted(paths)[:3])
            extra = len(paths) - 3
            if extra > 0:
                names += f" (+{extra} more)"
            parts.append(f"{label}: {names}")
        return "; ".join(parts)


def diff_snapshots(before: dict[Path, float], after: dict[Path, float]) -> FileChanges:
    """Compute added, modified, and deleted files between two snapshots."""
    changes = FileChanges()
    for path, mtime in after.items():
        if path not in before:
            changes.added.append(path)
        elif before[path] != mtime:
            changes.modified.append(path)
    for path in before:
        if path not in after:
            changes.deleted.append(path)
    return changes


class DevServer:
    """Run a server subprocess and restart it when watched files change."""

    def __init__(
        self,
        server_cmd: list[str],
        watch_dir: Path | str,
        *,
        extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
        interval: float = 1.0,
        cwd: Path | None = None,
        console: Console | None = None,
        max_crashes: int = 5,
    ) -> None:
        if not server_cmd:
            raise ValueError("server_cmd must not be empty")
        if interval <= 0:
            raise ValueError(f"interval must be positive, got {interval}")
        if not extensions:
            raise ValueError("extensions must not be empty")
        if max_crashes < 1:
            raise ValueError(f"max_crashes must be at least 1, got {max_crashes}")
        watch_path = Path(watch_dir)
        if not watch_path.is_dir():
            raise ValueError(f"watch directory does not exist: {watch_path}")

        self.server_cmd = server_cmd
        self.watch_dir = watch_path
        self.extensions = extensions
        self.interval = interval
        self.cwd = cwd
        self.max_crashes = max_crashes
        self.restart_count = 0
        self.gave_up = False
        self._consecutive_crashes = 0
        self._console = console or Console()
        self._process: subprocess.Popen[bytes] | None = None
        self._snapshot: dict[Path, float] = {}

    @property
    def is_running(self) -> bool:
        """True if the server process is alive."""
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Take the initial snapshot and start the server."""
        self._snapshot = snapshot_files(self.watch_dir, self.extensions)
        self._spawn()

    def stop(self) -> None:
        """Stop the server process if it is running."""
        if self._process is None:
            return
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        self._process = None

    def restart(self) -> None:
        """Stop and start the server, incrementing the restart counter."""
        self.stop()
        self._spawn()
        self.restart_count += 1

    def check_changes(self) -> FileChanges:
        """Take a fresh snapshot and return the diff against the previous one."""
        current = snapshot_files(self.watch_dir, self.extensions)
        changes = diff_snapshots(self._snapshot, current)
        self._snapshot = current
        return changes

    def poll_once(self) -> bool:
        """Run one watch iteration. Returns True if the server was restarted.

        Crashed servers are revived, but after max_crashes consecutive exits
        with no file change in between, the watcher gives up (gave_up is set)
        instead of hot-looping on a server that can never start.
        """
        if not self.is_running:
            self._consecutive_crashes += 1
            if self._consecutive_crashes >= self.max_crashes:
                self._console.print(
                    f"[red]Server exited {self._consecutive_crashes} times in a row, "
                    "giving up.[/red] Fix the error above and start again."
                )
                self.gave_up = True
                return False
            code = self._process.returncode if self._process else None
            self._console.print(
                f"[yellow]Server exited with code {code}, restarting...[/yellow]"
            )
            self._snapshot = snapshot_files(self.watch_dir, self.extensions)
            self.restart()
            return True

        self._consecutive_crashes = 0
        changes = self.check_changes()
        if changes.has_changes:
            self._console.print(
                f"[cyan]Change detected[/cyan] ({changes.describe()}), restarting..."
            )
            self.restart()
            return True
        return False

    def run(self, max_iterations: int | None = None) -> None:
        """Start the server and watch until interrupted.

        Args:
            max_iterations: Stop after this many watch ticks. None runs
                until KeyboardInterrupt. Mainly useful for testing.
        """
        try:
            self.start()
        except (FileNotFoundError, PermissionError) as exc:
            self._console.print(
                f"[red]Cannot start server:[/red] {exc}\n"
                f"[dim]Command: {' '.join(self.server_cmd)}[/dim]"
            )
            self.gave_up = True
            return
        self._console.print(
            f"[green]Dev server started[/green] (pid {self._process.pid if self._process else '?'}). "
            "Press Ctrl+C to stop."
        )
        iterations = 0
        try:
            while max_iterations is None or iterations < max_iterations:
                time.sleep(self.interval)
                iterations += 1
                self.poll_once()
                if self.gave_up:
                    break
        except KeyboardInterrupt:
            self._console.print("\n[dim]Interrupted.[/dim]")
        finally:
            self.stop()
            self._console.print(
                f"[green]Dev server stopped.[/green] Restarts this session: {self.restart_count}"
            )

    def _spawn(self) -> None:
        self._process = subprocess.Popen(self.server_cmd, cwd=self.cwd)
