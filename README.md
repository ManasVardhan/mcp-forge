
# 🔨 MCP Forge

> **New here?** Start with the [Getting Started Guide](GETTING_STARTED.md).

**Scaffold, test, and publish Model Context Protocol (MCP) servers in seconds.**

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()
[![PyPI](https://img.shields.io/badge/pypi-v0.1.1-orange.svg)]()

---

## The Problem

Building MCP servers involves too much boilerplate. Every new server needs the same JSON-RPC handling, tool definitions, resource handlers, Dockerfile, tests, and packaging config. You end up copying from old projects, fixing import paths, and wasting time on plumbing instead of building.

**MCP Forge fixes this.** One command generates a complete, ready-to-develop MCP server project. Another command tests it. Another validates compliance. Another publishes it.

## Features

- 🏗️ **Scaffold** full MCP server projects (tools, resources, prompts) in one command
- 🏪 **Template marketplace**: browse and install ready-made server templates from the builtin, a local, or an HTTP registry
- ➕ **Grow** existing projects: `mcp-forge add tool|resource|prompt` wires up new capabilities and their tests
- 🔥 **Hot reload** dev server that restarts on file changes
- 🧪 **Test** servers with a built-in MCP test harness (JSON-RPC over stdio)
- 🔍 **Validate** server compliance against the MCP specification, statically and live over stdio
- 📦 **Publish** to PyPI with a single command
- 🎨 **Jinja2-powered scaffolding** with clean, extensible templates
- 🐳 **Dockerfile** included in every generated project
- ⚡ **Zero config** needed for standard MCP servers

## Quick Start

### Install

```bash
pip install mcp-server-forge
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
│       ├── resources.py
│       └── prompts.py
└── tests/
    └── test_my_server.py
```

### Add tools, resources, and prompts later

Projects grow. Add tools, resources, or prompts to an existing project without hand-editing boilerplate:

```bash
cd my-server
mcp-forge add tool forecast alerts
mcp-forge add resource docs://readme
mcp-forge add prompt summarize
```

Each new tool gets a registry entry with input schema, a dispatch branch, a handler stub, and a generated test. Resources get a registry entry plus read tests; prompts get a definition, dispatch branch, handler stub, and get tests. If the project was scaffolded without resources or prompts, the server capability is wired into `server.py` automatically (import, initialize capabilities, and dispatch branches). The harness's expected lists are updated too, so `pytest` keeps passing while you fill in the real logic. Duplicate names, invalid names or URIs, and hand-mangled files are rejected with clear errors instead of corrupted code.

### Test your server

Every scaffolded project ships with a ready-to-run pytest harness in
`tests/`: one mock JSON-RPC call per tool, initialize handshake checks,
schema assertions, and error path coverage. It passes out of the box:

```bash
cd my-server
pip install -e '.[dev]'
pytest
# 11 passed
```

You can also exercise the server over real stdio with the black-box test runner:

```bash
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

### Develop with hot reload

```bash
mcp-forge dev ./my-server
```

Starts your server and watches the project for changes. Edit a file, and the server restarts automatically. If the server crashes, it gets revived. Stop with Ctrl+C.

```bash
# Custom launch command
mcp-forge dev ./my-server --cmd "uv run server.py"

# Watch different extensions or poll faster
mcp-forge dev ./my-server --ext py,yaml --interval 0.5
```

By default it watches `.py`, `.toml`, `.json`, and `.j2` files, skipping `__pycache__`, hidden directories, virtualenvs, and build output.

### Validate compliance

```bash
# Static structure checks
mcp-forge validate ./my-server

# Also boot the server and validate its live protocol responses
mcp-forge validate ./my-server --cmd 'python -m my_server.server'

# CI-friendly JSON report (exit code 1 on any error)
mcp-forge validate ./my-server --cmd 'python -m my_server.server' --json
```

### Publish

```bash
mcp-forge publish ./my-server
mcp-forge publish ./my-server --repository testpypi --dry-run
```

### Register with Claude Desktop

```bash
mcp-forge register ./my-server
```

Adds your server to `claude_desktop_config.json` so Claude Desktop can launch it. The default config location is detected per platform (macOS, Linux, Windows), and everything else in the file is preserved.

```bash
# Preview the change without writing
mcp-forge register ./my-server --dry-run

# Custom launch command and server name
mcp-forge register ./my-server --name weather --cmd "uv run server.py"

# Overwrite an existing entry
mcp-forge register ./my-server --force

# Remove the entry again
mcp-forge register ./my-server --remove
```

Restart Claude Desktop after registering to pick up the change.

## Scaffolding

The `new` command generates a complete MCP server with:

- A fully functional `server.py` with JSON-RPC request routing
- Tool definitions and handlers in `tools.py`
- Resource handlers in `resources.py`
- Prompt definitions and handlers in `prompts.py` (with `--prompts`)
- A `pyproject.toml` configured with hatchling
- A `Dockerfile` for containerized deployment
- A `README.md` with usage instructions
- Basic tests and `.gitignore`

### Options

```bash
mcp-forge new my-server \
  --tools weather,calculator,search \
  --resources "file://data,http://api" \
  --prompts summarize,code_review \
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
| `prompts.py.j2` | Prompt definitions and handlers |
| `project_pyproject.toml.j2` | Package configuration |
| `project_readme.md.j2` | Project README |
| `dockerfile.j2` | Docker container config |
| `init.py.j2` | Package init file |

## Template Marketplace

Start from a ready-made server template instead of a blank scaffold:

```bash
mcp-forge template list                        # Browse available templates
mcp-forge template show api-client             # Inspect one template
mcp-forge template install api-client my-api   # Install as a new project
```

Builtin templates:

| Template | What you get |
|----------|--------------|
| `starter` | Minimal server with a single hello tool |
| `api-client` | fetch and search tools plus a config resource, for wrapping HTTP APIs |
| `knowledge-base` | lookup tool, doc resources, and summarize plus answer prompts |

Installed projects are normal scaffolded servers: the generated pytest
harness passes out of the box, and templates can ship extra files (like
setup notes) into the project.

Registries are plain JSON, so you can host your own and point at it with
`--registry`:

```bash
mcp-forge template list --registry ./my-registry.json
mcp-forge template install team-server --registry https://example.com/registry.json
```

A registry is an object with a `templates` list; each template has a
`name`, `version`, `description`, `author`, its `tools`, `resources`,
and `prompts`, and optional `extra_files` (relative paths mapped to file
content, with `{{project_name}}` and `{{pkg_name}}` placeholders). Also
available in Python via `mcp_forge.marketplace`: `load_registry`,
`get_template`, and `install_template`.

## Testing

mcp-forge gives you two layers of testing.

**Generated pytest harness.** Every `mcp-forge new` project includes an
auto-generated `tests/test_<pkg>.py` that drives the server in-process with
mock JSON-RPC requests: the initialize handshake, `tools/list` contents, a
`tools/call` per scaffolded tool, input schema assertions, resource reads
and prompt gets (when resources or prompts are scaffolded), and error paths
for unknown tools, methods, resources, and prompts. Run it with
`pip install -e '.[dev]' && pytest`, then extend the per-tool tests as you
implement real logic.

**Black-box test runner.** `mcp-forge test` starts your MCP server as a
subprocess and sends JSON-RPC requests over stdio, validating:

- **Server startup** and clean shutdown
- **initialize** response with protocol version, capabilities, and server info
- **tools/list** returns valid tool definitions
- **tools/call** executes a tool and returns content
- **ping** responds correctly
- **Unknown methods** return proper JSON-RPC errors

Add `--json` for a machine-readable report (pass/fail counts plus every
result and raw response), with a nonzero exit code on failures for CI:

```bash
mcp-forge test --cmd 'python -m my_server.server' --json
```

## Validation

The `validate` command checks your project for:

- Required file structure (`src/`, `pyproject.toml`, `server.py`, `tools.py`)
- Tool definitions match the MCP schema (name, description, inputSchema)
- Initialize responses include all required fields
- Tool results contain valid content arrays

With `--cmd`, validation goes live: the server is booted over stdio and its
actual responses are checked against the MCP schemas:

- Initialize handshake returns protocolVersion, capabilities, and serverInfo
- `tools/list`, `resources/list`, and `prompts/list` payloads match the spec
- No duplicate tool, resource, or prompt names
- Declared capabilities match reality (a declared capability whose list
  endpoint errors is an error; served items without a declared capability
  are a warning)

Add `--json` for a machine-readable report with a nonzero exit code on
errors, ready for CI gates.

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
pip install mcp-server-forge[publish]
```

## Template Customization

The scaffolding uses Jinja2 templates internally. To customize the generated code, fork the repo and modify the templates in `src/mcp_forge/templates/`. The Jinja2 context includes:

- `project_name` - the project name as given
- `pkg_name` - Python package name (snake_case)
- `title` - human readable title
- `description` - project description
- `author` - author name
- `tools` - list of tool names
- `resources` - list of resource URI patterns
- `prompts` - list of prompt names

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
