"""ignition-mcp server entrypoint: builds the app context, registers all tool
modules and MCP resources, and runs over stdio."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .app import AppContext
from .bridge import BridgeClient
from .client import GatewayClient
from .config import load_settings

TEMPLATE_DIR = Path(__file__).parent / "perspective" / "templates"


def build_server() -> FastMCP:
    settings = load_settings()
    ctx = AppContext(
        settings=settings,
        client=GatewayClient(settings),
        bridge=BridgeClient(settings),
    )

    mcp = FastMCP(
        "ignition-mcp",
        instructions=(
            "Tools for Inductive Automation Ignition gateways: tags, tag history, alarms, "
            "projects, gateway admin, and full Perspective view deployment. "
            "Run ignition_diagnose first if anything fails. Mutating tools require the server "
            "to run with IGNITION_ALLOW_WRITES=true and confirm=true per call. "
            "Before authoring Perspective views, read the ignition://docs/view-schema resource "
            "and start from an ignition://templates/view/* template."
        ),
    )

    # Tool modules — each exposes register(mcp, ctx)
    from .tools import (
        alarms,
        bridge_admin,
        database,
        diagnostics,
        gateway,
        history,
        perspective,
        projects,
        tags,
    )

    for module in (
        diagnostics,
        tags,
        history,
        alarms,
        projects,
        perspective,
        gateway,
        database,
        bridge_admin,
    ):
        module.register(mcp, ctx)
        if hasattr(module, "register_extra"):
            module.register_extra(mcp, ctx)

    _register_resources(mcp)
    return mcp


def _register_resources(mcp: FastMCP) -> None:
    docs_dir = Path(__file__).parent / "perspective"

    @mcp.resource("ignition://docs/view-schema")
    def view_schema_doc() -> str:
        """Perspective view.json anatomy and authoring rules."""
        return (docs_dir / "VIEW_SCHEMA.md").read_text()

    for template_file in sorted(TEMPLATE_DIR.glob("*.json")):
        name = template_file.stem

        def make_reader(path: Path) -> Callable[[], str]:
            def read_template() -> str:
                return path.read_text()

            read_template.__name__ = f"template_{path.stem.replace('-', '_')}"
            read_template.__doc__ = f"Known-good Perspective view template: {path.stem}"
            return read_template

        mcp.resource(f"ignition://templates/view/{name}")(make_reader(template_file))


def main() -> None:
    try:
        server = build_server()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    server.run()


if __name__ == "__main__":
    main()
