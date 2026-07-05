from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..errors import ValidationError

AGGREGATION_MODES = (
    "Average",
    "MinMax",
    "LastValue",
    "SimpleAverage",
    "Sum",
    "Minimum",
    "Maximum",
    "Count",
    "Range",
    "Variance",
    "StdDev",
    "DurationOn",
    "DurationOff",
)


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def history_query(
        paths: list[str],
        start: str,
        end: str = "",
        aggregation: str = "Average",
        return_size: int = 300,
    ) -> dict[str, Any]:
        """Read-only, bridge plane. Query tag history."""
        if not paths or len(paths) > 20:
            raise ValidationError("paths must contain 1-20 tag paths")
        if aggregation not in AGGREGATION_MODES:
            raise ValidationError(f"aggregation must be one of {AGGREGATION_MODES}")
        if not 1 <= return_size <= 10000:
            raise ValidationError("return_size must be 1-10000")
        if not start:
            raise ValidationError("start must be non-empty")
        results = ctx.bridge.call(
            "history/query",
            {
                "paths": paths,
                "start": start,
                "end": end,
                "aggregation": aggregation,
                "returnSize": return_size,
            },
        )
        return {
            "query": {"paths": paths, "start": start, "end": end, "aggregation": aggregation},
            "data": results,
        }

    @mcp.tool()
    @tool_result(ctx)
    def history_providers() -> dict[str, Any]:
        """Read-only, bridge plane. List available history providers."""
        results = ctx.bridge.call("history/providers")
        return {"providers": results}
