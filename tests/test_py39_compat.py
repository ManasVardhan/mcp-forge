"""Regression tests: generated projects must stay Python 3.9 compatible.

A scaffolded server once used a match statement, which is 3.10+ syntax.
mcp-forge itself supports Python 3.9, so every file it generates must
parse at the 3.9 feature level.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from mcp_forge.scaffold import scaffold_project

MIN_FEATURE_VERSION = (3, 9)


def _generated_python_files(project: Path) -> list[Path]:
    files = sorted(project.rglob("*.py"))
    assert files, "expected scaffolded project to contain Python files"
    return files


class TestGeneratedCodeParsesOnPy39:
    def test_full_featured_project(self, tmp_path: Path) -> None:
        project = scaffold_project(
            "compat-server",
            output_dir=tmp_path,
            tools=["weather", "calculator"],
            resources=["notes://all"],
            prompts=["summarize"],
        )
        for py_file in _generated_python_files(project):
            source = py_file.read_text()
            try:
                ast.parse(source, filename=str(py_file), feature_version=MIN_FEATURE_VERSION)
            except SyntaxError as exc:
                pytest.fail(
                    f"{py_file.relative_to(project)} is not Python "
                    f"{'.'.join(map(str, MIN_FEATURE_VERSION))} compatible: {exc}"
                )

    def test_minimal_project(self, tmp_path: Path) -> None:
        project = scaffold_project("tiny-server", output_dir=tmp_path)
        for py_file in _generated_python_files(project):
            ast.parse(
                py_file.read_text(),
                filename=str(py_file),
                feature_version=MIN_FEATURE_VERSION,
            )

    def test_generated_pyproject_declares_39_floor(self, tmp_path: Path) -> None:
        project = scaffold_project("floor-server", output_dir=tmp_path)
        pyproject = (project / "pyproject.toml").read_text()
        assert 'requires-python = ">=3.9"' in pyproject
