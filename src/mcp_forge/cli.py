"""CLI interface for MCP Forge."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .scaffold import scaffold_project
from .tester import print_report, run_test_suite
from .validator import validate_project_structure, validate_tool_definitions

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="mcp-forge")
def cli() -> None:
    """🔨 MCP Forge - Scaffold, test, and publish MCP servers in seconds."""


@cli.command()
@click.argument("name")
@click.option("--tools", "-t", default="", help="Comma-separated list of tool names to scaffold.")
@click.option("--resources", "-r", default="", help="Comma-separated list of resource URI patterns.")
@click.option("--description", "-d", default="", help="Project description.")
@click.option("--author", "-a", default="", help="Author name.")
@click.option("--output-dir", "-o", type=click.Path(), default=".", help="Output directory.")
def new(name: str, tools: str, resources: str, description: str, author: str, output_dir: str) -> None:
    """Create a new MCP server project.

    Example: mcp-forge new my-server --tools weather,calculator
    """
    tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []
    resource_list = [r.strip() for r in resources.split(",") if r.strip()] if resources else []

    console.print(f"\n[bold]🔨 Forging new MCP server: [cyan]{name}[/cyan][/bold]\n")

    project_path = scaffold_project(
        name=name,
        output_dir=Path(output_dir),
        tools=tool_list,
        resources=resource_list,
        description=description,
        author=author,
    )

    console.print(f"[green]✓[/green] Project created at [bold]{project_path}[/bold]\n")

    # Show generated tree
    console.print("[dim]Generated structure:[/dim]")
    _print_tree(project_path, prefix="  ")
    console.print()
    console.print("[dim]Next steps:[/dim]")
    console.print(f"  cd {name}")
    console.print("  pip install -e .")
    console.print(f"  mcp-forge test --cmd 'python -m {name.replace('-', '_')}.server'")
    console.print()


def _print_tree(path: Path, prefix: str = "", is_last: bool = True) -> None:
    """Print a directory tree."""
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
    entries = [e for e in entries if not e.name.startswith(".") or e.name == ".gitignore"]
    for i, entry in enumerate(entries):
        is_last_entry = i == len(entries) - 1
        connector = "└── " if is_last_entry else "├── "
        console.print(f"{prefix}{connector}{entry.name}")
        if entry.is_dir():
            extension = "    " if is_last_entry else "│   "
            _print_tree(entry, prefix + extension, is_last_entry)


@cli.command()
@click.option("--cmd", required=True, help="Command to start the MCP server (e.g. 'python -m my_server.server').")
@click.option("--cwd", type=click.Path(exists=True), default=None, help="Working directory for the server.")
def test(cmd: str, cwd: str | None) -> None:
    """Run the MCP test suite against a server.

    Example: mcp-forge test --cmd 'python -m my_server.server'
    """
    console.print(f"\n[bold]🧪 Testing MCP server: [cyan]{cmd}[/cyan][/bold]\n")

    server_cmd = cmd.split()
    cwd_path = Path(cwd) if cwd else None

    report = run_test_suite(server_cmd, cwd=cwd_path)
    print_report(report, console)
    console.print()

    if report.failed > 0:
        raise SystemExit(1)


@cli.command()
@click.argument("project_dir", type=click.Path(exists=True))
def validate(project_dir: str) -> None:
    """Validate an MCP server project for compliance.

    Example: mcp-forge validate ./my-server
    """
    path = Path(project_dir)
    console.print(f"\n[bold]🔍 Validating: [cyan]{path.name}[/cyan][/bold]\n")

    report = validate_project_structure(path)

    if report.errors:
        for issue in report.errors:
            console.print(f"  [red]✗[/red] {issue.message}")
    if report.warnings:
        for issue in report.warnings:
            console.print(f"  [yellow]![/yellow] {issue.message}")

    if report.is_valid:
        console.print("  [green]✓ Project structure is valid![/green]")
    else:
        console.print(f"\n  [red]{len(report.errors)} error(s) found[/red]")
        raise SystemExit(1)

    console.print()


@cli.command()
@click.argument("project_dir", type=click.Path(exists=True), default=".")
@click.option("--repository", default="pypi", help="Target repository (pypi or testpypi).")
@click.option("--dry-run", is_flag=True, help="Build but do not upload.")
def publish(project_dir: str, repository: str, dry_run: bool) -> None:
    """Build and publish an MCP server package.

    Example: mcp-forge publish ./my-server
    """
    path = Path(project_dir)
    console.print(f"\n[bold]📦 Publishing: [cyan]{path.name}[/cyan][/bold]\n")

    # Build
    console.print("[dim]Building package...[/dim]")
    result = subprocess.run(
        [sys.executable, "-m", "build"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Build failed:[/red]\n{result.stderr}")
        raise SystemExit(1)

    console.print("[green]✓[/green] Package built successfully")

    if dry_run:
        console.print("[yellow]Dry run, skipping upload.[/yellow]")
        return

    # Upload
    repo_url = (
        "https://test.pypi.org/legacy/" if repository == "testpypi"
        else "https://upload.pypi.org/legacy/"
    )
    console.print(f"[dim]Uploading to {repository}...[/dim]")
    result = subprocess.run(
        [sys.executable, "-m", "twine", "upload", "--repository-url", repo_url, "dist/*"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print(f"[red]Upload failed:[/red]\n{result.stderr}")
        raise SystemExit(1)

    console.print(f"[green]✓[/green] Published to {repository}!")
    console.print()


if __name__ == "__main__":
    cli()
