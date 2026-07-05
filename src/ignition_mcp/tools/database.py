from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..errors import ValidationError
from ..guards import require_writes


def _first_word(sql: str) -> str:
    sql = sql.strip()
    lines = sql.split("\n")
    for line in lines:
        stripped_line = line.lstrip()
        if stripped_line.startswith("--"):
            continue
        if "/*" in stripped_line:
            index = stripped_line.index("/*")
            stripped_line = stripped_line[index:].lstrip()
        if stripped_line:
            return stripped_line.split()[0].lower()
    return ""


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def db_run_named_query(
        project: str, query_path: str, parameters: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Read-only by default, bridge plane. Runs a project Named Query."""
        if not project or not query_path:
            raise ValidationError("project and query_path must be non-empty")
        result = ctx.bridge.call(
            "db/named-query", {"project": project, "path": query_path, "params": parameters or {}}
        )
        return {"project": project, "query": query_path, "result": result}

    @mcp.tool()
    @tool_result(ctx)
    def db_query(
        sql: str, database: str = "", args: list[Any] | None = None, confirm: bool = False
    ) -> dict[str, Any]:
        """Bridge plane. SELECT statements run read-only; any other statement is mutating."""
        if not sql:
            raise ValidationError("sql must be non-empty")
        mutating = _first_word(sql) not in {"select", "show", "describe"}
        if mutating:
            require_writes(ctx.settings, confirm, "db_query")
        result = ctx.bridge.call(
            "db/query", {"sql": sql, "database": database, "args": args or [], "mutating": mutating}
        )
        return {"database": database or "(default)", "result": result, "mutating": mutating}
