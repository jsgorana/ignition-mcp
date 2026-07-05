from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..errors import ValidationError
from ..guards import require_tag_write_allowed, require_writes

IMPORT_COLLISION_POLICIES = ("Abort", "Overwrite", "Rename", "Ignore", "MergeOverwrite")


def _unwrap(result: Any, key: str) -> Any:
    """Bridge handlers return {'<key>': payload}; tolerate both shapes."""
    if isinstance(result, dict) and key in result:
        return result[key]
    return result


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def tag_browse(path: str = "", provider: str = "default", depth: int = 1) -> dict[str, Any]:
        """Read-only, bridge plane. Browse tags/folders."""
        if not (1 <= depth <= 5):
            raise ValidationError("depth must be 1-5")
        results = ctx.bridge.call(
            "tags/browse", {"path": path, "provider": provider, "depth": depth}
        )
        return {"path": path, "provider": provider, "results": _unwrap(results, "results")}

    @mcp.tool()
    @tool_result(ctx)
    def tag_read(paths: list[str]) -> dict[str, Any]:
        """Read-only, bridge plane. Read live values for 1-100 tag paths."""
        if not (1 <= len(paths) <= 100):
            raise ValidationError("paths must contain 1-100 tag paths")
        results = ctx.bridge.call("tags/read", {"paths": paths})
        return {"tags": _unwrap(results, "tags")}

    @mcp.tool()
    @tool_result(ctx)
    def tag_write(writes: list[dict[str, Any]], confirm: bool = False) -> dict[str, Any]:
        """Mutating, bridge plane. Each write dict: {"path": str, "value": Any}."""
        require_writes(ctx.settings, confirm, "tag_write")
        if not (1 <= len(writes) <= 20):
            raise ValidationError("writes must contain 1-20 entries")
        for i, w in enumerate(writes):
            if "path" not in w or "value" not in w:
                raise ValidationError(f"write entry {i} is missing 'path' or 'value'")
        require_tag_write_allowed(ctx.settings, [w["path"] for w in writes])
        results = ctx.bridge.call("tags/write", {"writes": writes})
        return {"results": _unwrap(results, "results")}

    @mcp.tool()
    @tool_result(ctx)
    def tag_config_export(provider: str = "default", base_path: str = "") -> dict[str, Any]:
        """Read-only, REST plane. Export tag configuration as JSON."""
        result = ctx.client.get_json(
            "tags/export",
            params={"provider": provider, "path": base_path, "type": "json"},
        )
        return {"provider": provider, "basePath": base_path, "config": result}

    @mcp.tool()
    @tool_result(ctx)
    def tag_config_import(
        provider: str,
        base_path: str,
        tags_json: dict[str, Any],
        collision_policy: str = "Abort",
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Mutating, REST plane. Import tag configuration JSON."""
        require_writes(ctx.settings, confirm, "tag_config_import")
        if collision_policy not in IMPORT_COLLISION_POLICIES:
            raise ValidationError(
                f"collision_policy must be one of {', '.join(IMPORT_COLLISION_POLICIES)}"
            )
        result = ctx.client.post_json(
            "tags/import",
            body=tags_json,
            params={
                "provider": provider,
                "path": base_path,
                "type": "json",
                "collisionPolicy": collision_policy,
            },
        )
        return {"imported": True, "result": result}

    @mcp.tool()
    @tool_result(ctx)
    def tag_create(
        base_path: str,
        tags: list[dict[str, Any]],
        collision_policy: str = "abort",
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Mutating, bridge plane. Create or update tags from config dicts."""
        require_writes(ctx.settings, confirm, "tag_create")
        if not (1 <= len(tags) <= 50):
            raise ValidationError("tags must contain 1-50 entries")
        if collision_policy not in ("abort", "merge", "overwrite"):
            raise ValidationError("collision_policy must be 'abort', 'merge', or 'overwrite'")
        results = ctx.bridge.call(
            "tags/configure",
            {"basePath": base_path, "tags": tags, "collisionPolicy": collision_policy[0]},
        )
        return {"results": _unwrap(results, "results")}
