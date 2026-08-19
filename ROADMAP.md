# Roadmap - mcp-forge

## Shipped

### 📖 Claude Desktop Registration (v0.1)
The `mcp-forge register` command adds or removes servers in `claude_desktop_config.json` with platform-aware default paths, dry-run preview, and safe config merging. See the README for usage.

### 🔥 Hot Reload Dev Server (v0.1)
The `mcp-forge dev` command runs your server and watches project files, restarting automatically on changes (and reviving crashed servers). Configurable watch extensions and poll interval, no extra dependencies. See the README for usage.

### 🧪 Built-in Test Harness (v0.1)
Scaffolded projects now include an auto-generated pytest suite with mock JSON-RPC tool calls: initialize handshake, tools/list contents, one test per tool, schema assertions, resource reads, and error paths. Projects get a `dev` extra with pytest and the suite passes out of the box.

### 💬 MCP Prompts Scaffolding (v0.1)
The `new` command accepts `--prompts` to scaffold MCP prompt definitions: a generated `prompts.py` with prompts/list and prompts/get handlers, server capability wiring, generated tests per prompt, and `mcp-forge inspect` now displays a server's prompts.

### 🩺 Live Protocol Validation (v0.1)
`mcp-forge validate --cmd` boots the server over stdio and validates its live responses against the MCP schemas: initialize handshake, tools/resources/prompts list payloads, duplicate names, and capability/reality mismatches. A `--json` flag emits a CI-friendly report with a nonzero exit code on errors.

### 🐍 Python 3.9 Support for Generated Servers (v0.1)
Scaffolded servers now use plain if/elif dispatch instead of match statements, so generated projects run on Python 3.9 and newer, matching mcp-forge's own floor. Generated pyproject files declare `requires-python = ">=3.9"`, CI tests 3.9 through 3.13, and a regression test parses every generated file at the 3.9 feature level.

### 🧾 JSON Test Reports (v0.1)
`mcp-forge test --cmd ... --json` emits the full test report as JSON (pass/fail counts, per-result messages, raw JSON-RPC responses) with a nonzero exit code on failures, matching the CI-friendly output of `validate --json`.

### ➕ Add Tools to Existing Projects (v0.1)
The `mcp-forge add tool` command grows a scaffolded project in place: each new tool gets a TOOLS registry entry with input schema, a dispatch branch, a handler stub, and a generated harness test, with the expected tools/list assertion updated so pytest keeps passing. Duplicate names, invalid names, and hand-mangled files are rejected with clear errors.

### ➕ Add Resources and Prompts (v0.2)
`mcp-forge add resource` and `mcp-forge add prompt` grow scaffolded projects in place: resources get RESOURCES registry entries with derived names, prompts get PROMPTS definitions with dispatch branches and handler stubs. Projects scaffolded without either capability get server.py wired automatically (import, initialize capabilities, dispatch branches before ping). Generated tests are extended or appended so pytest keeps passing, and invalid URIs, duplicate entries, and hand-mangled files are rejected with clear errors.

## v0.2 (Planned)

### 🏪 Template Marketplace
Browse and install community-contributed MCP server templates. Publish your own templates with `mcp-forge publish`.

---

Have ideas? Open an issue or start a discussion!
