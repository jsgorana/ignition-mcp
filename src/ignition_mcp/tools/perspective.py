from __future__ import annotations

import json
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..errors import GatewayError, ValidationError
from ..guards import require_name_echo, require_writes
from ..perspective.schema import validate_view

PERSPECTIVE = "com.inductiveautomation.perspective"


def _view_dir(project: str, view_path: str) -> str:
    """Relative path (under data/projects/) of a view folder."""
    return f"{project}/{PERSPECTIVE}/views/{view_path}"


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def perspective_list_views(project: str) -> dict[str, Any]:
        """Read-only, bridge plane."""
        if not project:
            raise ValidationError("project must be non-empty")
        result = ctx.bridge.call(
            "files/list", {"path": f"{project}/{PERSPECTIVE}/views", "recursive": True}
        )
        entries = result.get("entries", result) if isinstance(result, dict) else result
        prefix = f"{project}/{PERSPECTIVE}/views/"
        suffix = "/view.json"
        view_paths = []
        for entry in entries:
            p = entry["path"]
            if p.endswith(suffix):
                if p.startswith(prefix):
                    p = p[len(prefix) :]
                view_paths.append(p[: -len(suffix)])
        return {"project": project, "views": sorted(view_paths)}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_get_view(project: str, view_path: str) -> dict[str, Any]:
        """Read-only, bridge plane."""
        if not project or not view_path:
            raise ValidationError("both project and view_path must be non-empty")
        raw = ctx.bridge.call("files/read", {"path": _view_dir(project, view_path) + "/view.json"})
        try:
            view = json.loads(raw["content"])
        except json.JSONDecodeError as exc:
            raise GatewayError(f"view.json is not valid JSON: {exc}") from exc
        return {"project": project, "view_path": view_path, "view": view}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_upsert_view(
        project: str, view_path: str, view_json: dict[str, Any], confirm: bool = False
    ) -> dict[str, Any]:
        """Mutating, bridge plane + REST scan."""
        require_writes(ctx.settings, confirm, "perspective_upsert_view")
        if not project or not view_path:
            raise ValidationError("project and view_path must be non-empty")
        if ".." in view_path or view_path.startswith("/"):
            raise ValidationError("view_path must be a relative path without ..")
        problems = validate_view(view_json)
        if problems:
            raise ValidationError(f"view_json failed validation: {'; '.join(problems)}")
        ctx.bridge.call(
            "files/write",
            {
                "path": _view_dir(project, view_path) + "/view.json",
                "content": json.dumps(view_json, indent=2),
            },
        )
        ctx.bridge.call(
            "files/write",
            {
                "path": _view_dir(project, view_path) + "/resource.json",
                "content": json.dumps(
                    {
                        "scope": "G",
                        "version": 1,
                        "restricted": False,
                        "overridable": True,
                        "files": ["view.json"],
                        "attributes": {},
                    },
                    indent=2,
                ),
            },
        )
        scan = ctx.client.scan_projects()
        return {"project": project, "view_path": view_path, "deployed": True, "scan": scan}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_delete_view(
        project: str, view_path: str, confirm_name: str = "", confirm: bool = False
    ) -> dict[str, Any]:
        """Mutating + destructive, bridge plane + REST scan."""
        require_writes(ctx.settings, confirm, "perspective_delete_view")
        require_name_echo(view_path, confirm_name, "perspective_delete_view")
        ctx.bridge.call("files/delete", {"path": _view_dir(project, view_path), "recursive": True})
        scan = ctx.client.scan_projects()
        return {"project": project, "deleted_view": view_path, "scan": scan}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_validate_view(view_json: dict[str, Any]) -> dict[str, Any]:
        """Read-only, local (no gateway call)."""
        problems = validate_view(view_json)
        return {"valid": len(problems) == 0, "problems": problems}


def register_extra(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def perspective_page_config_get(project: str) -> dict[str, Any]:
        """Read-only, bridge plane."""
        try:
            raw = ctx.bridge.call(
                "files/read", {"path": f"{project}/{PERSPECTIVE}/page-config/config.json"}
            )
            return {"project": project, "pages": json.loads(raw["content"])}
        except GatewayError:
            return {"project": project, "pages": {}}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_page_config_set(
        project: str, page_url: str, view_path: str, title: str = "", confirm: bool = False
    ) -> dict[str, Any]:
        """Mutating, bridge plane + scan. Read-modify-write: never clobber other pages."""
        require_writes(ctx.settings, confirm, "perspective_page_config_set")
        if not page_url.startswith("/"):
            raise ValidationError("page_url must start with /")
        try:
            raw = ctx.bridge.call(
                "files/read", {"path": f"{project}/{PERSPECTIVE}/page-config/config.json"}
            )
            config = json.loads(raw["content"])
        except (GatewayError, ValueError):
            config = {"pages": {}}
        config["pages"][page_url] = {"viewPath": view_path, "title": title or view_path}
        ctx.bridge.call(
            "files/write",
            {
                "path": f"{project}/{PERSPECTIVE}/page-config/config.json",
                "content": json.dumps(config, indent=2),
            },
        )
        scan = ctx.client.scan_projects()
        return {"project": project, "page": page_url, "view": view_path, "scan": scan}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_session_props_get(project: str) -> dict[str, Any]:
        """Read-only, bridge plane."""
        try:
            raw = ctx.bridge.call(
                "files/read", {"path": f"{project}/{PERSPECTIVE}/session-props/props.json"}
            )
            return {"project": project, "props": json.loads(raw["content"])}
        except GatewayError:
            return {"project": project, "props": {}}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_style_upsert(
        project: str, style_class: str, style_json: dict[str, Any], confirm: bool = False
    ) -> dict[str, Any]:
        """Mutating, bridge plane + scan."""
        require_writes(ctx.settings, confirm, "perspective_style_upsert")
        if not re.match(r"^[A-Za-z0-9_/-]+$", style_class):
            raise ValidationError("style_class must match ^[A-Za-z0-9_/-]+$")
        base = f"{project}/{PERSPECTIVE}/style-classes/{style_class}"
        ctx.bridge.call(
            "files/write",
            {"path": f"{base}/style.json", "content": json.dumps(style_json, indent=2)},
        )
        ctx.bridge.call(
            "files/write",
            {
                "path": f"{base}/resource.json",
                "content": json.dumps(
                    {
                        "scope": "G",
                        "version": 1,
                        "restricted": False,
                        "overridable": True,
                        "files": ["style.json"],
                        "attributes": {},
                    },
                    indent=2,
                ),
            },
        )
        scan = ctx.client.scan_projects()
        return {"project": project, "style_class": style_class, "scan": scan}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_list_sessions() -> dict[str, Any]:
        """Read-only, REST plane (Perspective module API)."""
        result = ctx.client.get_json("/data/perspective/api/v1/sessions")
        return {"sessions": result}

    @mcp.tool()
    @tool_result(ctx)
    def perspective_bootstrap_project(
        project: str, title: str = "", confirm: bool = False
    ) -> dict[str, Any]:
        """Mutating, REST + bridge + scan. One-call working Perspective app."""
        require_writes(ctx.settings, confirm, "perspective_bootstrap_project")
        if not re.match(r"^[A-Za-z0-9_]+$", project):
            raise ValidationError("project must match ^[A-Za-z0-9_]+$")
        ctx.client.post_json(
            "projects",
            body={
                "name": project,
                "title": title or project,
                "description": "Created by ignition-mcp",
                "parent": "",
                "inheritable": False,
                "enabled": True,
            },
        )
        view = {
            "custom": {},
            "params": {},
            "props": {"defaultSize": {"height": 600, "width": 800}},
            "root": {
                "children": [
                    {
                        "meta": {"name": "WelcomeLabel"},
                        "position": {"basis": "auto"},
                        "props": {"text": "Deployed by ignition-mcp"},
                        "type": "ia.display.label",
                    }
                ],
                "meta": {"name": "root"},
                "props": {"direction": "column"},
                "type": "ia.container.flex",
            },
        }
        ctx.bridge.call(
            "files/write",
            {
                "path": f"{project}/{PERSPECTIVE}/views/Home/view.json",
                "content": json.dumps(view, indent=2),
            },
        )
        ctx.bridge.call(
            "files/write",
            {
                "path": f"{project}/{PERSPECTIVE}/views/Home/resource.json",
                "content": json.dumps(
                    {
                        "scope": "G",
                        "version": 1,
                        "restricted": False,
                        "overridable": True,
                        "files": ["view.json"],
                        "attributes": {},
                    },
                    indent=2,
                ),
            },
        )
        page_config = {"pages": {"/": {"viewPath": "Home", "title": title or project}}}
        ctx.bridge.call(
            "files/write",
            {
                "path": f"{project}/{PERSPECTIVE}/page-config/config.json",
                "content": json.dumps(page_config, indent=2),
            },
        )
        scan = ctx.client.scan_projects()
        return {
            "project": project,
            "url": f"{ctx.settings.gateway_url}/data/perspective/client/{project}",
            "views": ["Home"],
            "scan": scan,
        }
