<p align="center">
  <img src="assets/hero.svg" alt="mcp-forge" width="800">
</p>

# 🔨 MCP Forge

**Scaffold, test, and publish Model Context Protocol (MCP) servers in seconds.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()
[![PyPI](https://img.shields.io/badge/pypi-v0.1.0-orange.svg)]()

---

## The Problem

Building MCP servers involves too much boilerplate. Every new server needs the same JSON-RPC handling, tool definitions, resource handlers, Dockerfile, tests, and packaging config. You end up copying from old projects, fixing import paths, and wasting time on plumbing instead of building.

**MCP Forge fixes this.** One command generates a complete, production-ready MCP server project. Another command tests it. Another validates compliance. Another publishes it.

## Features

- 🏗️ **Scaffold** full MCP server projects from templates in one command
- 🧪 **Test** servers with a built-in MCP test harness (JSON-RPC over stdio)
- 🔍 **Validate** server compliance against the MCP specification
- 📦 **Publish** to PyPI with a single command
- 🎨 **Custom templates** with Jinja2 for your own conventions
- 🐳 **Dockerfile** included in every generated project
- ⚡ **Zero config** needed for standard MCP servers

## Quick Start

### Install

```bash
pip install mcp-forge
```

### Create a new MCP server

```bash
mcp-forge new my-server --tools weather,calculator
```

That's it. You now have a complete, runnable MCP server:

```
my-server/
├── Dockerfile
├── README.md
├── pyproject.toml
├── .gitignore
├── src/
│   └── my_server/
│       ├── __init__.py
│       ├── server.py
│       ├── tools.py
│       └── resources.py
└── tests/
    └── test_my_server.py
```

### Test your server

```bash
cd my-server
pip install -e .
mcp-forge test --cmd 'python -m my_server.server'
```

```
┌──────────────────────────────────────────────────┐
│           MCP Forge Test Results                 │
├──────────────┬────────┬──────────────────────────┤
│ Test         │ Status │ Details                  │
├──────────────┼────────┼──────────────────────────┤
│ server_start │  PASS  │ Server started           │
│ initialize   │  PASS  │ initialize response valid │
│ tools/list   │  PASS  │ Found 2 tools            │
│ tools/call   │  PASS  │ Called 'weather' OK      │
│ ping         │  PASS  │ Ping OK                  │
│ unknown      │  PASS  │ Correctly returned error │
│ server_stop  │  PASS  │ Server stopped cleanly   │
├──────────────┴────────┴──────────────────────────┤
│ 7/7 passed  All tests passed!                    │
└──────────────────────────────────────────────────┘
```

### Validate compliance

```bash
mcp-forge validate ./my-server
```

### Publish

```bash
mcp-forge publish ./my-server
mcp-forge publish ./my-server --repository testpypi --dry-run
```

## Scaffolding

The `new` command generates a complete MCP server with:

- A fully functional `server.py` with JSON-RPC request routing
- Tool definitions and handlers in `tools.py`
- Resource handlers in `resources.py`
- A `pyproject.toml` configured with hatchling
- A `Dockerfile` for containerized deployment
- A `README.md` with usage instructions
- Basic tests and `.gitignore`

### Options

```bash
mcp-forge new my-server \
  --tools weather,calculator,search \
  --resources "file://data,http://api" \
  --description "My awesome MCP server" \
  --author "Your Name" \
  --output-dir ./projects
```

## Templates

MCP Forge uses Jinja2 templates internally. Each generated file comes from a template in the `templates/` directory:

| Template | Generates |
|----------|-----------|
| `server.py.j2` | Main server with JSON-RPC routing |
| `tools.py.j2` | Tool definitions and handlers |
| `resources.py.j2` | Resource definitions and handlers |
| `project_pyproject.toml.j2` | Package configuration |
| `project_readme.md.j2` | Project README |
| `dockerfile.j2` | Docker container config |
| `init.py.j2` | Package init file |

## Testing

The built-in test harness starts your MCP server as a subprocess and sends JSON-RPC requests over stdio, validating:

- **Server startup** and clean shutdown
- **initialize** response with protocol version, capabilities, and server info
- **tools/list** returns valid tool definitions
- **tools/call** executes a tool and returns content
- **ping** responds correctly
- **Unknown methods** return proper JSON-RPC errors

## Validation

The `validate` command checks your project for:

- Required file structure (`src/`, `pyproject.toml`, `server.py`, `tools.py`)
- Tool definitions match the MCP schema (name, description, inputSchema)
- Initialize responses include all required fields
- Tool results contain valid content arrays

## Publishing

The `publish` command wraps `build` and `twine` for a smooth publishing experience:

```bash
# Build and publish to PyPI
mcp-forge publish .

# Dry run (build only)
mcp-forge publish . --dry-run

# Publish to TestPyPI
mcp-forge publish . --repository testpypi
```

Make sure you have `build` and `twine` installed:

```bash
pip install mcp-forge[publish]
```

## Custom Templates

Want to customize the generated code? Fork the repo and modify the templates in `src/mcp_forge/templates/`. The Jinja2 context includes:

- `project_name` - the project name as given
- `pkg_name` - Python package name (snake_case)
- `title` - human readable title
- `description` - project description
- `author` - author name
- `tools` - list of tool names
- `resources` - list of resource URI patterns

## Development

```bash
git clone https://github.com/manasvardhan/mcp-forge.git
cd mcp-forge
pip install -e ".[dev]"
pytest
```

## License

MIT License. See [LICENSE](LICENSE) for details.

---

Built with 🔨 by [Manas Vardhan](https://github.com/manasvardhan)
