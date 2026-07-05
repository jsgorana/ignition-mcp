from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..errors import ValidationError
from ..guards import require_name_echo, require_writes


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def project_list() -> dict[str, Any]:
        """Read-only, REST plane. List all projects."""
        result = ctx.client.get_json("projects/list")
        return {"projects": result.get("items", []) if isinstance(result, dict) else result}

    @mcp.tool()
    @tool_result(ctx)
    def project_get(name: str) -> dict[str, Any]:
        """Read-only, REST plane. Get details for one project."""
        if not name:
            raise ValidationError("name is required")
        result = ctx.client.get_json(f"projects/find/{name}")
        return {"project": result}

    @mcp.tool()
    @tool_result(ctx)
    def project_create(
        name: str,
        title: str = "",
        description: str = "",
        parent: str = "",
        inheritable: bool = False,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Mutating, REST plane. Create a new project."""
        require_writes(ctx.settings, confirm, "project_create")
        if not re.match(r"^[A-Za-z0-9_]+$", name):
            raise ValidationError("project name must match ^[A-Za-z0-9_]+$")
        result = ctx.client.post_json(
            "projects",
            body={
                "name": name,
                "title": title or name,
                "description": description,
                "parent": parent,
                "inheritable": inheritable,
                "enabled": True,
            },
        )
        return {"created": name, "result": result}

    @mcp.tool()
    @tool_result(ctx)
    def project_delete(name: str, confirm_name: str = "", confirm: bool = False) -> dict[str, Any]:
        """Mutating + destructive, REST plane. Delete a project."""
        require_writes(ctx.settings, confirm, "project_delete")
        require_name_echo(name, confirm_name, "project_delete")
        ctx.client.delete_json(f"projects/{name}")
        return {"deleted": name}

    @mcp.tool()
    @tool_result(ctx)
    def project_export(name: str, save_to: str = "") -> dict[str, Any]:
        """Read-only, REST plane. Export a project zip."""
        if not name:
            raise ValidationError("name is required")
        data = ctx.client.get_bytes(f"projects/export/{name}")
        if not save_to:
            return {
                "project": name,
                "size_bytes": len(data),
                "note": "pass save_to=<absolute path ending .zip> to write the archive to disk",
            }
        if not save_to.endswith(".zip"):
            raise ValidationError("save_to must end with .zip")
        Path(save_to).write_bytes(data)
        return {"project": name, "saved_to": save_to, "size_bytes": len(data)}

    @mcp.tool()
    @tool_result(ctx)
    def project_import(name: str, zip_path: str, confirm: bool = False) -> dict[str, Any]:
        """Mutating, REST plane. Import a project zip as project <name>."""
        require_writes(ctx.settings, confirm, "project_import")
        if not zip_path.endswith(".zip") or not Path(zip_path).is_file():
            raise ValidationError(f"zip file not found: {zip_path}")
        content = Path(zip_path).read_bytes()
        result = ctx.client.post_bytes(
            f"projects/import/{name}",
            content,
            "application/zip",
            params={"overwrite": "true"},
        )
        return {"imported": name, "result": result}

    @mcp.tool()
    @tool_result(ctx)
    def project_scan() -> dict[str, Any]:
        """Safe trigger, REST plane. Request a scan of external project files."""
        result = ctx.client.scan_projects()
        return {"scan": "requested", "result": result}
