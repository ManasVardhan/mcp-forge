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
```

## Code Style

- Python 3.10+ with type hints throughout
- Use `from __future__ import annotations` in all modules
- Follow PEP 8

## Pull Requests

1. Fork the repo and create a branch from `main`
2. Add tests for any new functionality
3. Make sure all tests pass
4. Update documentation if needed
5. Open a PR with a clear description

## Reporting Issues

Open an issue on GitHub with:

- A clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
