# AGENTS.md - MCP Forge

## Overview
- Scaffold, test, validate, and publish Model Context Protocol (MCP) servers in seconds. One command generates a complete, ready-to-develop MCP server project with JSON-RPC routing, tool definitions, resource handlers, Dockerfile, tests, and packaging config.
- For developers building MCP servers who want to skip boilerplate and focus on tool logic.
- Core value: Jinja2-powered project scaffolding, built-in MCP test harness (JSON-RPC over stdio), spec compliance validation, and PyPI publishing workflow.

## Architecture

```
+----------------+     +------------------+     +-------------------+
|   CLI (click)  | --> |   Scaffold       | --> | Generated Project |
|  new, test,    |     | (Jinja2 templates|     |   src/pkg/        |
|  validate,     |     |  project gen)    |     |     server.py     |
|  publish       |     +------------------+     |     tools.py      |
+----------------+            |                 |     resources.py  |
       |                      v                 |   pyproject.toml  |
       |              +------------------+      |   Dockerfile      |
       +----->        |   Tester         |      +-------------------+
       |              | (MCPTestClient,  |
       |              |  JSON-RPC stdio) |
       |              +------------------+
       |
       +----->  +------------------+     +-------------------+
                |   Validator      |     |   Publisher        |
                | (structure check,|     | (build + twine)    |
                |  JSON Schema)    |     +-------------------+
                +------------------+
```

**Data flow:**
1. `mcp-forge new <name>` renders Jinja2 templates with project context (name, tools, resources, author)
2. Output is a complete project directory with server.py, tools.py, resources.py, pyproject.toml, Dockerfile, tests
3. `mcp-forge test --cmd '...'` starts the server as a subprocess, sends JSON-RPC requests over stdio, validates responses
4. `mcp-forge validate ./project` checks file structure and tool definitions against MCP JSON Schemas
5. `mcp-forge publish ./project` runs `python -m build` then `twine upload`

## Directory Structure

```
mcp-forge/
  .github/workflows/ci.yml        -- CI: test + coverage + mypy on Python 3.10-3.13
  src/mcp_forge/
    __init__.py                    -- __version__ = "0.1.1"
    cli.py                         -- Click CLI: new, test, validate, publish
    scaffold.py                    -- scaffold_project(), template rendering, name validation
    tester.py                      -- MCPTestClient, run_test_suite(), print_report()
    validator.py                   -- validate_project_structure(), JSON Schemas for tools/resources/initialize/results
    templates/                     -- Jinja2 templates (server.py.j2, tools.py.j2, etc.)
  examples/
    weather_server/                -- Example generated MCP server
      src/weather_server/
        __init__.py
        server.py
        tools.py
        resources.py
      pyproject.toml
  tests/                           -- 203 tests across 12 test files
    test_scaffold.py               -- Scaffold generation tests
    test_scaffold_extended.py      -- Extended scaffold tests
    test_tester.py                 -- Test harness tests
    test_tester_extended.py        -- Extended tester tests
    test_validator.py              -- Validation tests
    test_validator_extended.py     -- Extended validation tests
    test_cli.py                    -- CLI command tests
    test_cli_extended.py           -- Extended CLI tests
    test_cli_publish_test.py       -- Publish command tests
    test_integration.py            -- Integration tests
    test_edge_cases.py             -- Edge case coverage
  pyproject.toml                   -- Hatchling build, metadata
  README.md                        -- Full docs
  ROADMAP.md                       -- v0.2 plans
  CONTRIBUTING.md                  -- Contribution guidelines
  GETTING_STARTED.md               -- Quick start guide
  LICENSE                          -- MIT
```

## Core Concepts

- **Scaffolding**: Jinja2 templates rendered with project context. Templates: `server.py.j2` (JSON-RPC routing), `tools.py.j2` (tool handlers), `resources.py.j2` (resource handlers), `project_pyproject.toml.j2`, `project_readme.md.j2`, `dockerfile.j2`, `init.py.j2`.
- **Template context**: `project_name`, `pkg_name` (snake_case), `title` (Title Case), `description`, `author`, `tools` (list of tool names), `resources` (list of resource URIs).
- **MCPTestClient**: Starts an MCP server as a subprocess, communicates via stdin/stdout JSON-RPC. Sends requests with `send_request()`, notifications with `send_notification()`.
- **TestReport / TestResult**: Aggregate results from the test suite. Each test (server_start, initialize, tools/list, tools/call, ping, unknown_method, server_stop) produces a TestResult with pass/fail and message.
- **Validator**: Checks project structure (pyproject.toml, src/ dir, server.py, tools.py exist). Also validates tool definitions, resource definitions, initialize responses, and tool results against JSON Schemas.
- **JSON Schemas**: `TOOL_SCHEMA` (name, description, inputSchema), `INITIALIZE_RESPONSE_SCHEMA` (protocolVersion, capabilities, serverInfo), `TOOL_RESULT_SCHEMA` (content array), `RESOURCE_SCHEMA` (uri, name).
- **ValidationReport**: List of ValidationIssue objects (level=error|warning, category, message). `.is_valid` checks for zero errors.

## API Reference

### scaffold_project()
```python
def scaffold_project(
    name: str,
    output_dir: Path | None = None,
    tools: Sequence[str] = (),
    resources: Sequence[str] = (),
    description: str = "",
    author: str = "",
) -> Path  # returns path to generated project root
```

### MCPTestClient
```python
class MCPTestClient:
    def __init__(self, server_cmd: list[str], cwd: Path | None = None)
    def start(self) -> None
    def stop(self) -> None
    def send_request(self, method: str, params: dict | None = None) -> dict
    def send_notification(self, method: str, params: dict | None = None) -> None
```

### run_test_suite()
```python
def run_test_suite(server_cmd: list[str], cwd: Path | None = None) -> TestReport
```

### Validation
```python
def validate_project_structure(project_dir: Path) -> ValidationReport
def validate_tool_definitions(tools: list[dict]) -> ValidationReport
def validate_resource_definitions(resources: list[dict]) -> ValidationReport
def validate_initialize_response(response: dict) -> ValidationReport
def validate_tool_result(result: dict) -> ValidationReport
```

### Helpers
```python
def snake_case(name: str) -> str          # "my-server" -> "my_server"
def title_case(name: str) -> str          # "my-server" -> "My Server"
def validate_project_name(name: str) -> None   # raises ValueError
def validate_tool_names(tools) -> None         # raises ValueError
```

## CLI Commands

```bash
# Create a new MCP server project
mcp-forge new my-server --tools weather,calculator --resources "file://data" --description "My server" --author "Your Name" --output-dir ./projects

# Test a running MCP server
mcp-forge test --cmd 'python -m my_server.server' --cwd ./my-server

# Validate project structure and compliance
mcp-forge validate ./my-server

# Build and publish to PyPI
mcp-forge publish ./my-server
mcp-forge publish ./my-server --dry-run
mcp-forge publish ./my-server --repository testpypi

# Version
mcp-forge --version
```

## Configuration

- **No config files or env vars** for core functionality
- **Generated projects** use Hatchling as build backend
- **Publishing** requires `build` and `twine` (`pip install mcp-server-forge[publish]`)
- **Template customization**: Fork the repo and modify templates in `src/mcp_forge/templates/`

## Testing

```bash
pip install -e ".[dev]"
pytest --cov=mcp_forge --cov-report=term-missing
```

- **203 tests** across 12 test files
- Tests use temporary directories for scaffold generation
- Located in `tests/`

## Dependencies

- **click>=8.1**: CLI framework
- **jinja2>=3.1**: Template rendering for scaffolding
- **rich>=13.0**: Terminal output (tables, trees, colors)
- **jsonschema>=4.20**: MCP spec validation
- **build>=1.0** (optional, `[publish]` extra): Package building
- **twine>=4.0** (optional, `[publish]` extra): PyPI uploading
- **Python >=3.9** (note: lower than other repos in the suite)

## CI/CD

- **GitHub Actions** (`.github/workflows/ci.yml`)
- Matrix: Python 3.10, 3.11, 3.12, 3.13
- Steps: install, pytest with coverage, mypy (continue-on-error)
- Triggers: push/PR to main

## Current Status

- **Version**: 0.1.1
- **Published on PyPI**: yes (`pip install mcp-server-forge`)
- **What works**: Full project scaffolding with Jinja2 templates, MCP test harness (JSON-RPC over stdio), project structure validation, tool/resource/initialize/result JSON Schema validation, PyPI publish workflow, example weather server
- **Known limitations**: No template marketplace. No hot reload dev server. No Claude Desktop integration helper.
- **Roadmap (v0.2)**: Template marketplace, hot reload dev server, Claude Desktop integration guide, built-in test harness for generated projects

## Development Guide

```bash
git clone https://github.com/manasvardhan/mcp-forge.git
cd mcp-forge
pip install -e ".[dev]"
pytest
```

- **Build system**: Hatchling
- **Source layout**: `src/mcp_forge/`
- **Adding a new template**: Create `.j2` file in `src/mcp_forge/templates/`, add to `file_map` in `scaffold.py`
- **Adding a new validation check**: Add to `validate_project_structure()` or create new `validate_*()` function in `validator.py`
- **Adding a new test to the harness**: Add test case in `run_test_suite()` in `tester.py`
- **Code style**: Ruff, line length 100, target Python 3.10. Mypy with warn_return_any.

## Git Conventions

- **Branch**: main
- **Commits**: Imperative style ("Add feature X", "Fix bug Y")
- Never use em dashes in commit messages or docs

## Context

- **Author**: Manas Vardhan (ManasVardhan on GitHub)
- **Part of**: A suite of AI agent tooling
- **Related repos**: llm-cost-guardian (cost tracking), agent-sentry (crash reporting), agent-replay (trace debugging), llm-shelter (safety guardrails), promptdiff (prompt versioning), bench-my-llm (benchmarking)
- **PyPI package**: `mcp-server-forge`
- **Import as**: `mcp_forge`
