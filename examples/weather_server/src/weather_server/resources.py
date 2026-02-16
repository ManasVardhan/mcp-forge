"""Resource handlers for Weather Server."""

from __future__ import annotations

from typing import Any

RESOURCES: list[dict[str, Any]] = []


async def handle_resource_read(uri: str) -> dict[str, Any]:
    """Read a resource by URI."""
    raise ValueError(f"Unknown resource: {uri}")
