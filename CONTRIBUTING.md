# Contributing to MCP Forge

Thanks for your interest in contributing! Here's how to get started.

## Setup

```bash
git clone https://github.com/manasvardhan/mcp-forge.git
cd mcp-forge
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
pytest --cov=mcp_forge
pytest --cov=mcp_forge --cov-report=term-missing
```

## Code Quality

We use **ruff** for linting and **mypy** for type checking:

```bash
pip install ruff mypy types-jsonschema
ruff check src/ tests/
mypy src/
```

### Style Guidelines

- Python 3.10+ with type hints throughout
- Use `from __future__ import annotations` in all modules
- Follow PEP 8
- Line length: 100 characters max
- Docstrings on all public functions and classes

## Project Structure

```
src/mcp_forge/
    __init__.py          # Package version
    cli.py               # Click CLI commands
    scaffold.py          # Project scaffolding logic
    tester.py            # MCP test client and test suite
    validator.py         # MCP spec validation
    templates/           # Jinja2 templates for scaffolding
```

## Pull Requests

1. Fork the repo and create a branch from `main`
2. Add tests for any new functionality
3. Make sure all tests pass (`pytest`)
4. Run linting (`ruff check src/ tests/`)
5. Update documentation if needed
6. Open a PR with a clear description

## Good First Issues

Check the [good first issues](https://github.com/manasvardhan/mcp-forge/labels/good%20first%20issue) label for beginner-friendly tasks.

## Reporting Issues

Open an issue on GitHub with:

- A clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
- Output of `mcp-forge --version`

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
