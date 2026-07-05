from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..errors import ValidationError
from ..guards import require_writes

ALARM_STATES = ("ActiveUnacked", "ActiveAcked", "ClearUnacked", "ClearAcked")


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def alarm_status(
        states: list[str] | None = None,
        min_priority: str = "Low",
        source_filter: str = "*",
        display_path_filter: str = "*",
        limit: int = 100,
    ) -> dict[str, Any]:
        """Read-only, bridge plane. Query current alarm status."""
        if states and not all(state in ALARM_STATES for state in states):
            raise ValidationError(f"Invalid states: {states}. Valid states are {ALARM_STATES}")
        if min_priority not in ("Diagnostic", "Low", "Medium", "High", "Critical"):
            raise ValidationError(
                f"Invalid min_priority: {min_priority}. Valid priorities are "
                "Diagnostic, Low, Medium, High, Critical"
            )
        if not 1 <= limit <= 500:
            raise ValidationError("limit must be 1-500")
        results = ctx.bridge.call(
            "alarms/status",
            {
                "states": states or list(ALARM_STATES),
                "minPriority": min_priority,
                "source": source_filter,
                "displayPath": display_path_filter,
                "limit": limit,
            },
        )
        if isinstance(results, dict) and "alarms" in results:
            return {
                "alarms": results["alarms"],
                "truncated": results.get("truncated", False),
                "limit": limit,
            }
        return {"alarms": results, "limit": limit}

    @mcp.tool()
    @tool_result(ctx)
    def alarm_journal(
        start: str,
        end: str = "",
        states: list[str] | None = None,
        source_filter: str = "*",
        limit: int = 200,
    ) -> dict[str, Any]:
        """Read-only, bridge plane. Query the alarm journal over a time range."""
        if not start:
            raise ValidationError("start must be non-empty")
        if not 1 <= limit <= 1000:
            raise ValidationError("limit must be 1-1000")
        if states and not all(state in ALARM_STATES for state in states):
            raise ValidationError(f"Invalid states: {states}. Valid states are {ALARM_STATES}")
        results = ctx.bridge.call(
            "alarms/journal",
            {
                "start": start,
                "end": end,
                "states": states or list(ALARM_STATES),
                "source": source_filter,
                "limit": limit,
            },
        )
        if isinstance(results, dict) and "events" in results:
            return {
                "events": results["events"],
                "truncated": results.get("truncated", False),
                "limit": limit,
            }
        return {"events": results, "limit": limit}

    @mcp.tool()
    @tool_result(ctx)
    def alarm_acknowledge(
        event_ids: list[str], notes: str = "", confirm: bool = False
    ) -> dict[str, Any]:
        """Mutating, bridge plane. Acknowledge alarms by event UUID."""
        require_writes(ctx.settings, confirm, "alarm_acknowledge")
        if not 1 <= len(event_ids) <= 100:
            raise ValidationError("event_ids must contain 1-100 event IDs")
        results = ctx.bridge.call("alarms/ack", {"eventIds": event_ids, "notes": notes})
        return {"acknowledged": results}
