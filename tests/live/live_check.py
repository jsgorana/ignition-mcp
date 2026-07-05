"""Live integration check against a real Ignition gateway.

Run manually:
    IGNITION_URL=... IGNITION_API_TOKEN=... IGNITION_BRIDGE_SECRET=... \
    IGNITION_ALLOW_WRITES=true python tests/live/live_check.py

Exercises the full v1 surface end-to-end, including a Perspective deploy
round-trip, using a dedicated mcp_it_demo project namespace. Prints a summary
table; exits non-zero on any FAIL.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from ignition_mcp.app import AppContext
from ignition_mcp.bridge import BridgeClient
from ignition_mcp.client import GatewayClient
from ignition_mcp.config import load_settings

PROJECT = "mcp_it_demo"
results: list[tuple[str, str, str]] = []


class ToolBox:
    """Register modules like the real server and expose tools by name."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, *a: Any, **k: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[fn.__name__] = fn
            return fn

        return deco

    def resource(self, *a: Any, **k: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return deco


def check(name: str, fn: Callable[[], Any]) -> Any:
    try:
        value = fn()
        results.append((name, "PASS", ""))
        return value
    except AssertionError as exc:
        results.append((name, "FAIL", str(exc)))
    except Exception as exc:  # noqa: BLE001 — report, don't crash the suite
        results.append((name, "FAIL", f"{type(exc).__name__}: {exc}"))
    return None


def main() -> int:
    settings = load_settings()
    ctx = AppContext(
        settings=settings, client=GatewayClient(settings), bridge=BridgeClient(settings)
    )
    box = ToolBox()
    from ignition_mcp.tools import (
        alarms,
        database,
        diagnostics,
        gateway,
        history,
        perspective,
        projects,
        tags,
    )

    for m in (diagnostics, tags, history, alarms, projects, perspective, gateway, database):
        m.register(box, ctx)
        if hasattr(m, "register_extra"):
            m.register_extra(box, ctx)
    t = box.tools
    print(f"registered {len(t)} tools")

    # ---- diagnostics
    def _diagnose() -> None:
        d = t["ignition_diagnose"]()
        print(json.dumps(d, indent=1))
        assert d["healthy"], f"diagnose unhealthy: {d}"

    check("ignition_diagnose", _diagnose)

    def _trial_reset() -> None:
        r = t["gateway_trial_reset"](confirm=True)
        assert "error" not in r, r
        assert r["trial"]["trialSecondsLeft"] > 7000, r["trial"]

    check("gateway_trial_reset", _trial_reset)

    check("gateway_info", lambda: _expect_no_error(t["gateway_info"]()))
    check("gateway_modules", lambda: _expect_no_error(t["gateway_modules"]()))
    check("gateway_performance", lambda: _expect_no_error(t["gateway_performance"]()))

    # ---- tags
    def _tag_create() -> None:
        r = t["tag_create"](
            base_path="[default]McpDemo",
            tags=[
                {
                    "name": "Value1",
                    "tagType": "AtomicTag",
                    "valueSource": "memory",
                    "dataType": "Int4",
                    "value": 11,
                },
                {
                    "name": "Value2",
                    "tagType": "AtomicTag",
                    "valueSource": "memory",
                    "dataType": "Float8",
                    "value": 2.5,
                },
            ],
            collision_policy="overwrite",
            confirm=True,
        )
        assert "error" not in r, r

    check("tag_create", _tag_create)

    def _tag_write_read() -> None:
        w = t["tag_write"](writes=[{"path": "[default]McpDemo/Value1", "value": 42}], confirm=True)
        assert "error" not in w, w
        r = t["tag_read"](paths=["[default]McpDemo/Value1", "[default]McpDemo/Value2"])
        assert "error" not in r, r
        v1 = r["tags"][0]
        assert v1["value"] == 42, v1
        assert "Good" in v1["quality"], v1

    check("tag_write+tag_read", _tag_write_read)

    def _tag_browse() -> None:
        r = t["tag_browse"](path="McpDemo", provider="default", depth=1)
        assert "error" not in r, r
        names = {n["name"] for n in r["results"]}
        assert {"Value1", "Value2"} <= names, names

    check("tag_browse", _tag_browse)

    check(
        "tag_config_export",
        lambda: _expect_no_error(t["tag_config_export"](base_path="McpDemo")),
    )

    # ---- alarms (empty result acceptable; structure must be sane)
    def _alarm_status() -> None:
        r = t["alarm_status"](limit=10)
        assert "error" not in r, r
        assert isinstance(r["alarms"], list), r

    check("alarm_status", _alarm_status)

    # ---- history (no historian datasource configured — expect structured error)
    def _history() -> None:
        r = t["history_query"](paths=["[default]McpDemo/Value1"], start="-1h")
        assert isinstance(r, dict), r
        # Either data (if historian available) or a structured, actionable error.
        assert "data" in r or "error" in r, r

    check("history_query (structured either way)", _history)

    # ---- perspective full round-trip
    def _bootstrap() -> None:
        t["project_delete"](name=PROJECT, confirm_name=PROJECT, confirm=True)  # clean slate
        r = t["perspective_bootstrap_project"](project=PROJECT, title="MCP IT Demo", confirm=True)
        assert "error" not in r, r

    check("perspective_bootstrap_project", _bootstrap)

    def _list_views() -> None:
        r = t["perspective_list_views"](project=PROJECT)
        assert "error" not in r, r
        assert "Home" in r["views"], r

    check("perspective_list_views", _list_views)

    def _upsert_view() -> None:
        view = {
            "custom": {},
            "params": {},
            "props": {"defaultSize": {"height": 400, "width": 600}},
            "root": {
                "type": "ia.container.flex",
                "meta": {"name": "root"},
                "props": {"direction": "column"},
                "children": [
                    {
                        "type": "ia.display.label",
                        "meta": {"name": "TagLabel"},
                        "position": {"basis": "auto"},
                        "props": {"text": ""},
                        "propConfig": {
                            "props.text": {
                                "binding": {
                                    "type": "tag",
                                    "config": {
                                        "mode": "direct",
                                        "tagPath": "[default]McpDemo/Value1",
                                    },
                                }
                            }
                        },
                    }
                ],
            },
        }
        r = t["perspective_upsert_view"](
            project=PROJECT, view_path="Live/TagView", view_json=view, confirm=True
        )
        assert "error" not in r, r
        g = t["perspective_get_view"](project=PROJECT, view_path="Live/TagView")
        assert g["view"]["root"]["children"][0]["meta"]["name"] == "TagLabel", g

    check("perspective_upsert_view+get_view", _upsert_view)

    def _page_config() -> None:
        r = t["perspective_page_config_set"](
            project=PROJECT, page_url="/live", view_path="Live/TagView", confirm=True
        )
        assert "error" not in r, r
        g = t["perspective_page_config_get"](project=PROJECT)
        assert "/live" in g["pages"]["pages"], g
        assert "/" in g["pages"]["pages"], "bootstrap page clobbered"

    check("perspective_page_config set/get", _page_config)

    def _perspective_serves() -> None:
        import time

        import httpx

        url = f"{settings.gateway_url}/data/perspective/client/{PROJECT}"
        code = 0
        for _ in range(10):
            code = httpx.get(url, follow_redirects=True, timeout=20).status_code
            if code == 200:
                return
            time.sleep(2)
        raise AssertionError(f"{url} -> {code} after retries")

    check("perspective client page serves", _perspective_serves)

    check("perspective_list_sessions", lambda: _expect_no_error(t["perspective_list_sessions"]()))

    def _delete_view() -> None:
        r = t["perspective_delete_view"](
            project=PROJECT,
            view_path="Live/TagView",
            confirm_name="Live/TagView",
            confirm=True,
        )
        assert "error" not in r, r
        lst = t["perspective_list_views"](project=PROJECT)
        assert "Live/TagView" not in lst["views"], lst

    check("perspective_delete_view", _delete_view)

    # ---- projects
    def _export() -> None:
        r = t["project_export"](name=PROJECT)
        assert r.get("size_bytes", 0) > 0, r

    check("project_export", _export)

    def _project_cleanup() -> None:
        r = t["project_delete"](name=PROJECT, confirm_name=PROJECT, confirm=True)
        assert "error" not in r, r

    check("project_delete (cleanup)", _project_cleanup)

    # ---- db (no datasource — expect structured error, not crash)
    def _db() -> None:
        r = t["db_query"](sql="SELECT 1")
        assert isinstance(r, dict), r

    check("db_query (structured either way)", _db)

    check("gateway_logs_query", lambda: _expect_no_error(t["gateway_logs_query"](limit=5)))

    # ---- guard sanity on live server
    def _guard() -> None:
        r = t["tag_write"](writes=[{"path": "[default]McpDemo/Value1", "value": 1}])
        assert r.get("error") == "write_not_allowed", r

    check("write guard refuses without confirm", _guard)

    # ---- report
    print()
    width = max(len(n) for n, _, _ in results)
    failed = 0
    for name, status, detail in results:
        print(f"{name.ljust(width)}  {status}  {detail[:120]}")
        failed += status == "FAIL"
    print(f"\n{len(results) - failed}/{len(results)} live checks passed")
    return 1 if failed else 0


def _expect_no_error(r: dict) -> dict:
    assert isinstance(r, dict) and "error" not in r, r
    return r


if __name__ == "__main__":
    sys.exit(main())
