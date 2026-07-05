from __future__ import annotations

import pathlib
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..errors import ValidationError
from ..guards import require_writes


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def gateway_modules() -> dict[str, Any]:
        """Read-only, REST plane."""
        healthy = ctx.client.get_json("modules/healthy")
        quarantined = ctx.client.get_json("modules/quarantined")
        items = healthy.get("items", healthy) if isinstance(healthy, dict) else healthy
        return {"modules": items, "quarantined": quarantined}

    @mcp.tool()
    @tool_result(ctx)
    def gateway_logs_query(
        level: str = "INFO", logger: str = "", text: str = "", limit: int = 100
    ) -> dict[str, Any]:
        """Read-only, REST plane."""
        if level not in ("TRACE", "DEBUG", "INFO", "WARN", "ERROR"):
            raise ValidationError("level must be one of TRACE, DEBUG, INFO, WARN, ERROR")
        if not (1 <= limit <= 500):
            raise ValidationError("limit must be 1-500")
        params = {"minimumLevel": level, "limit": limit}
        if logger:
            params["loggerName"] = logger
        if text:
            params["message"] = text
        result = ctx.client.get_json("logs", params=params)
        return {"logs": result, "limit": limit}

    @mcp.tool()
    @tool_result(ctx)
    def gateway_logger_set_level(
        logger_name: str, level: str, confirm: bool = False
    ) -> dict[str, Any]:
        """Mutating, REST plane."""
        require_writes(ctx.settings, confirm, "gateway_logger_set_level")
        if level not in ("TRACE", "DEBUG", "INFO", "WARN", "ERROR", "OFF"):
            raise ValidationError("level must be one of TRACE, DEBUG, INFO, WARN, ERROR, OFF")
        if not logger_name:
            raise ValidationError("logger_name is required")
        result = ctx.client.post_json(f"logs/loggers/{logger_name}", params={"level": level})
        return {"logger": logger_name, "level": level, "result": result}

    @mcp.tool()
    @tool_result(ctx)
    def gateway_backup(save_to: str, confirm: bool = False) -> dict[str, Any]:
        """Mutating-safe (heavy read), REST plane. Download a .gwbk gateway backup."""
        require_writes(ctx.settings, confirm, "gateway_backup")
        if not save_to.endswith(".gwbk"):
            raise ValidationError("save_to must end with .gwbk")
        data = ctx.client.get_bytes("backup")
        pathlib.Path(save_to).write_bytes(data)
        return {"saved_to": save_to, "size_bytes": len(data)}

    @mcp.tool()
    @tool_result(ctx)
    def gateway_performance() -> dict[str, Any]:
        """Read-only, REST plane."""
        overview = ctx.client.get_json("overview")
        problems = ctx.client.get_json("overview/problems")
        return {"overview": overview, "problems": problems}

    @mcp.tool()
    @tool_result(ctx)
    def config_resource_list(module: str = "ignition", resource_type: str = "") -> dict[str, Any]:
        """Read-only, REST plane. Generic gateway config resource listing."""
        if not resource_type:
            raise ValidationError(
                "resource_type is required, e.g. 'database-connection', "
                "'opc-connection', 'tag-provider'"
            )
        result = ctx.client.get_json(f"resources/list/{module}/{resource_type}")
        return {"module": module, "type": resource_type, "resources": result}
