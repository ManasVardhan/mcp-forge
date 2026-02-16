"""Tool definitions for Weather Server."""

from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "weather",
        "description": "Get current weather for a location",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "City name or location",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "forecast",
        "description": "Get weather forecast for a location",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "City name or location",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days to forecast",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
]


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call by name."""
    if name == "weather":
        return await _tool_weather(arguments)
    if name == "forecast":
        return await _tool_forecast(arguments)
    raise ValueError(f"Unknown tool: {name}")


async def _tool_weather(arguments: dict[str, Any]) -> dict[str, Any]:
    """Get current weather (mock implementation)."""
    city = arguments.get("query", "Unknown")
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Current weather in {city}:\n"
                    f"Temperature: 72F (22C)\n"
                    f"Conditions: Partly cloudy\n"
                    f"Humidity: 45%\n"
                    f"Wind: 8 mph NW"
                ),
            }
        ]
    }


async def _tool_forecast(arguments: dict[str, Any]) -> dict[str, Any]:
    """Get weather forecast (mock implementation)."""
    city = arguments.get("query", "Unknown")
    days = arguments.get("days", 3)
    lines = [f"{days}-day forecast for {city}:"]
    sample_temps = [(72, "Sunny"), (68, "Cloudy"), (75, "Clear"), (65, "Rain"), (70, "Partly cloudy")]
    for i in range(min(days, 5)):
        temp, cond = sample_temps[i]
        lines.append(f"  Day {i + 1}: {temp}F - {cond}")
    return {
        "content": [{"type": "text", "text": "\n".join(lines)}]
    }
