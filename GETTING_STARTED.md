# Getting Started with mcp-forge

A step-by-step guide to get up and running from scratch.

## Prerequisites

You need **Python 3.10 or newer** installed on your machine.

**Check if you have Python:**
```bash
python3 --version
```
If you see `Python 3.10.x` or higher, you're good. If not, download it from [python.org](https://www.python.org/downloads/).

## Step 1: Clone the repository

```bash
git clone https://github.com/ManasVardhan/mcp-forge.git
cd mcp-forge
```

## Step 2: Create a virtual environment

```bash
python3 -m venv venv
```

**Activate it:**

- **Mac/Linux:** `source venv/bin/activate`
- **Windows:** `venv\Scripts\activate`

## Step 3: Install the package

```bash
pip install -e ".[dev]"
```

## Step 4: Run the tests

```bash
pytest tests/ -v
```

All 23 tests should pass.

## Step 5: Try it out

### 5a. Scaffold a new MCP server

```bash
mcp-forge new my-first-server --tools weather,calculator
```

This generates a complete MCP server project. Take a look at what was created:

```bash
ls -la my-first-server/
```

You should see:
```
my-first-server/
  src/
    server.py          # Main server with JSON-RPC handler
    tools/
      weather.py       # Weather tool stub
      calculator.py    # Calculator tool stub
  tests/
    test_server.py     # Test file
  pyproject.toml       # Package config
  Dockerfile           # Container config
  README.md            # Auto-generated docs
```

### 5b. Look at the generated server

Open `my-first-server/src/server.py` in any text editor. You'll see a working MCP server with:
- JSON-RPC stdio transport (how AI models communicate with MCP servers)
- Tool handler routing
- Proper error handling

### 5c. Validate the server

Check that the generated server follows the MCP specification:

```bash
mcp-forge validate my-first-server/
```

You should see all checks passing.

### 5d. Test the server

```bash
mcp-forge test my-first-server/
```

This sends test JSON-RPC requests to your server and shows the responses.

### 5e. Check out the example weather server

There's a pre-built example in the repo:

```bash
ls examples/weather_server/
```

### 5f. Try different tool combinations

```bash
mcp-forge new api-server --tools search,translate,summarize
```

Each tool gets its own file with a stub implementation ready to fill in.

## Step 6: Build your own MCP server

1. Scaffold it:
   ```bash
   mcp-forge new my-custom-server --tools mytool
   ```

2. Edit `my-custom-server/src/tools/mytool.py` to add your logic

3. Test it:
   ```bash
   mcp-forge test my-custom-server/
   ```

4. Validate it:
   ```bash
   mcp-forge validate my-custom-server/
   ```

## Step 7: Run the linter (optional)

```bash
ruff check src/ tests/
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `python3: command not found` | Install Python from [python.org](https://www.python.org/downloads/) |
| `No module named mcp_forge` | Make sure you ran `pip install -e ".[dev]"` with the venv activated |
| `mcp-forge: command not found` | Make sure your venv is activated |
| Tests fail | Make sure you're on the latest `main` branch: `git pull origin main` |

## What's next?

- Read the full [README](README.md) for custom templates, publishing, and advanced options
- Check `examples/weather_server/` for a complete working MCP server
- Try connecting your MCP server to Claude Desktop or another MCP-compatible AI client
