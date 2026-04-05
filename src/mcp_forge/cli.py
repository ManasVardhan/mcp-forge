"""CLI interface for MCP Forge."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

from . import __version__
from .scaffold import scaffold_project
from .tester import MCPTestClient, print_report, run_test_suite
from .validator import validate_project_structure

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

    try:
        project_path = scaffold_project(
            name=name,
            output_dir=Path(output_dir),
            tools=tool_list,
            resources=resource_list,
            description=description,
            author=author,
        )
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1)

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


@cli.command()
@click.option("--cmd", required=True, help="Command to start the MCP server.")
@click.option("--cwd", type=click.Path(exists=True), default=None, help="Working directory for the server.")
@click.option("--json-output", is_flag=True, help="Output as JSON instead of rich tables.")
def inspect(cmd: str, cwd: str | None, json_output: bool) -> None:
    """Inspect a running MCP server's capabilities.

    Connects to a server, runs initialize, and displays all
    tools, resources, and server info.

    Example: mcp-forge inspect --cmd 'python -m my_server.server'
    """
    import json as json_mod

    server_cmd = cmd.split()
    cwd_path = Path(cwd) if cwd else None

    client = MCPTestClient(server_cmd, cwd=cwd_path)

    try:
        client.start()
    except Exception as exc:
        console.print(f"[red]Failed to start server:[/red] {exc}")
        raise SystemExit(1)

    try:
        # Initialize
        init_resp = client.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mcp-forge-inspector", "version": __version__},
        })

        init_result = init_resp.get("result", {})
        server_info = init_result.get("serverInfo", {})
        capabilities = init_result.get("capabilities", {})
        protocol_version = init_result.get("protocolVersion", "unknown")

        # Send initialized notification
        client.send_notification("notifications/initialized")

        # List tools
        tools_resp = client.send_request("tools/list")
        tools = tools_resp.get("result", {}).get("tools", [])

        # List resources
        resources_resp = client.send_request("resources/list")
        resources = resources_resp.get("result", {}).get("resources", [])

    except Exception as exc:
        console.print(f"[red]Error communicating with server:[/red] {exc}")
        client.stop()
        raise SystemExit(1)

    client.stop()

    if json_output:
        data = {
            "serverInfo": server_info,
            "protocolVersion": protocol_version,
            "capabilities": capabilities,
            "tools": tools,
            "resources": resources,
        }
        click.echo(json_mod.dumps(data, indent=2))
        return

    # Rich output
    from rich.panel import Panel
    from rich.table import Table

    console.print()
    console.print(Panel(
        f"[bold cyan]{server_info.get('name', 'Unknown')}[/] "
        f"v{server_info.get('version', '?')}\n"
        f"Protocol: {protocol_version}\n"
        f"Capabilities: {', '.join(capabilities.keys()) or 'none'}",
        title="[bold]🔍 MCP Server Info[/]",
        border_style="cyan",
    ))

    if tools:
        tool_table = Table(
            title=f"Tools ({len(tools)})",
            border_style="green",
            show_lines=True,
        )
        tool_table.add_column("Name", style="bold cyan")
        tool_table.add_column("Description")
        tool_table.add_column("Parameters", style="dim")

        for tool in tools:
            params = tool.get("inputSchema", {}).get("properties", {})
            param_names = ", ".join(params.keys()) if params else "none"
            tool_table.add_row(
                tool.get("name", "?"),
                tool.get("description", ""),
                param_names,
            )
        console.print(tool_table)
    else:
        console.print("[dim]No tools registered.[/dim]")

    if resources:
        res_table = Table(
            title=f"Resources ({len(resources)})",
            border_style="yellow",
            show_lines=True,
        )
        res_table.add_column("URI", style="bold yellow")
        res_table.add_column("Name")
        res_table.add_column("MIME Type", style="dim")

        for res in resources:
            res_table.add_row(
                res.get("uri", "?"),
                res.get("name", ""),
                res.get("mimeType", ""),
            )
        console.print(res_table)

    console.print()


@cli.command()
@click.argument("project_dir", type=click.Path(exists=True), default=".")
@click.option("--format", "fmt", type=click.Choice(["text", "json", "markdown"]),
              default="text", help="Output format.")
def info(project_dir: str, fmt: str) -> None:
    """Show project metadata and stats.

    Reads pyproject.toml and scans the source to report tools,
    resources, and structure info.

    Example: mcp-forge info ./my-server
    """
    import json as json_mod
    import re

    path = Path(project_dir)

    # Read pyproject.toml
    pyproject_path = path / "pyproject.toml"
    if not pyproject_path.exists():
        console.print(f"[red]No pyproject.toml found in {path}[/]")
        raise SystemExit(1)

    toml_text = pyproject_path.read_text()

    # Extract basic metadata from pyproject.toml (simple regex, no toml dep)
    name_match = re.search(r'^name\s*=\s*"([^"]+)"', toml_text, re.MULTILINE)
    version_match = re.search(r'^version\s*=\s*"([^"]+)"', toml_text, re.MULTILINE)
    desc_match = re.search(r'^description\s*=\s*"([^"]+)"', toml_text, re.MULTILINE)

    proj_name = name_match.group(1) if name_match else "unknown"
    proj_version = version_match.group(1) if version_match else "unknown"
    proj_desc = desc_match.group(1) if desc_match else ""

    # Scan source for tool/resource definitions
    src_dir = path / "src"
    py_files = list(src_dir.rglob("*.py")) if src_dir.exists() else []
    total_lines = 0
    for f in py_files:
        try:
            total_lines += len(f.read_text().splitlines())
        except Exception:
            pass

    # Check structure
    validation = validate_project_structure(path)

    has_tests = (path / "tests").exists() and any((path / "tests").glob("test_*.py"))
    has_docker = (path / "Dockerfile").exists()
    has_ci = (path / ".github" / "workflows").exists()
    has_readme = (path / "README.md").exists()

    data = {
        "name": proj_name,
        "version": proj_version,
        "description": proj_desc,
        "source_files": len(py_files),
        "total_lines": total_lines,
        "valid_structure": validation.is_valid,
        "errors": len(validation.errors),
        "warnings": len(validation.warnings),
        "has_tests": has_tests,
        "has_dockerfile": has_docker,
        "has_ci": has_ci,
        "has_readme": has_readme,
    }

    if fmt == "json":
        click.echo(json_mod.dumps(data, indent=2))
        return

    if fmt == "markdown":
        lines = [
            f"# {proj_name} v{proj_version}",
            "",
            f"> {proj_desc}" if proj_desc else "",
            "",
            f"- Source files: {len(py_files)}",
            f"- Total lines: {total_lines:,}",
            f"- Valid structure: {'Yes' if validation.is_valid else 'No'}",
            f"- Tests: {'Yes' if has_tests else 'No'}",
            f"- Dockerfile: {'Yes' if has_docker else 'No'}",
            f"- CI: {'Yes' if has_ci else 'No'}",
            f"- README: {'Yes' if has_readme else 'No'}",
        ]
        click.echo("\n".join(lines))
        return

    # Rich text output
    from rich.panel import Panel
    from rich.table import Table

    console.print()
    console.print(Panel(
        f"[bold cyan]{proj_name}[/] v{proj_version}\n{proj_desc}",
        title="[bold]📋 Project Info[/]",
        border_style="cyan",
    ))

    table = Table(border_style="blue", show_lines=True)
    table.add_column("Property", style="bold")
    table.add_column("Value")

    checks = [
        ("Source Files", str(len(py_files))),
        ("Total Lines", f"{total_lines:,}"),
        ("Valid Structure", "[green]Yes[/]" if validation.is_valid else f"[red]No ({len(validation.errors)} errors)[/]"),
        ("Tests", "[green]Yes[/]" if has_tests else "[red]No[/]"),
        ("Dockerfile", "[green]Yes[/]" if has_docker else "[yellow]No[/]"),
        ("CI/CD", "[green]Yes[/]" if has_ci else "[yellow]No[/]"),
        ("README", "[green]Yes[/]" if has_readme else "[red]No[/]"),
    ]

    for prop, val in checks:
        table.add_row(prop, val)

    console.print(table)
    console.print()


if __name__ == "__main__":
    cli()
