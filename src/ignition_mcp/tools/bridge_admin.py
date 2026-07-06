"""Bridge lifecycle tools: install and verify the mcp-bridge WebDev project."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..bridge import MIN_BRIDGE_VERSION
from ..errors import BridgeUnavailableError, ValidationError
from ..guards import require_writes

SECRET_PLACEHOLDER = "__BRIDGE_SECRET__"
LIB_ARCNAME = "ignition/script-python/mcp_bridge_lib/code.py"

# Matches only the `BRIDGE_SECRET = '__BRIDGE_SECRET__'` assignment line, not the
# gateway-side "is this configured?" guard that also references the placeholder
# (`if BRIDGE_SECRET == '__BRIDGE_SECRET__'`). A blind text-wide replace would
# substitute the guard too, making it compare the secret against itself and
# always report "not configured" even on a correct install.
_ASSIGNMENT_RE = re.compile(
    r"^BRIDGE_SECRET = '" + re.escape(SECRET_PLACEHOLDER) + r"'$", re.MULTILINE
)


def _find_bridge_zip() -> Path:
    """Locate mcp-bridge.zip in the installed package or the source checkout."""
    candidates = [
        Path(__file__).parent.parent / "_bridge" / "mcp-bridge.zip",  # packaged
        Path(__file__).parent.parent.parent.parent / "bridge" / "mcp-bridge.zip",  # repo
    ]
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


BRIDGE_ZIP = _find_bridge_zip()


def _zip_with_secret(secret: str) -> bytes:
    """Return the bridge zip with the secret substituted into the script library."""
    if not BRIDGE_ZIP.is_file():
        raise BridgeUnavailableError(
            f"Bridge archive not found at {BRIDGE_ZIP}. Run `python bridge/build_zip.py` first."
        )
    src = zipfile.ZipFile(BRIDGE_ZIP)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == LIB_ARCNAME:
                text = data.decode("utf-8")
                match = _ASSIGNMENT_RE.search(text)
                if not match:
                    raise BridgeUnavailableError(
                        "Bridge archive is missing the secret placeholder; rebuild it."
                    )
                start, end = match.span()
                text = text[:start] + f"BRIDGE_SECRET = {secret!r}" + text[end:]
                data = text.encode("utf-8")
            dst.writestr(info, data)
    return out_buf.getvalue()


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def bridge_install(confirm: bool = False) -> dict[str, Any]:
        """Install/upgrade the mcp-bridge WebDev project on the gateway. Mutating, REST plane.

        Uses IGNITION_BRIDGE_SECRET as the shared HMAC secret. After import, verifies
        the bridge responds to a signed ping."""
        require_writes(ctx.settings, confirm, "bridge_install")
        if not ctx.settings.bridge_secret:
            raise ValidationError(
                "IGNITION_BRIDGE_SECRET must be set before installing the bridge.",
                remediation="Generate a random secret and set IGNITION_BRIDGE_SECRET, then retry.",
            )
        payload = _zip_with_secret(ctx.settings.bridge_secret)
        ctx.client.post_bytes(
            "projects/import/mcp-bridge",
            payload,
            "application/zip",
            params={"overwrite": "true"},
        )
        ctx.client.scan_projects()
        try:
            pong = ctx.bridge.ping()
        except BridgeUnavailableError as exc:
            return {
                "installed": True,
                "verified": False,
                "note": str(exc),
            }
        return {"installed": True, "verified": True, "bridge_version": pong.get("version")}

    @mcp.tool()
    @tool_result(ctx)
    def bridge_status() -> dict[str, Any]:
        """Report bridge availability and version. Read-only, bridge plane."""
        if not ctx.settings.bridge_enabled:
            return {"enabled": False, "note": "IGNITION_BRIDGE_SECRET not set."}
        pong = ctx.bridge.ping()
        version = pong.get("version", "unknown")
        return {
            "enabled": True,
            "version": version,
            "min_supported": MIN_BRIDGE_VERSION,
            "capabilities": pong.get("capabilities", []),
        }


# expose helper for tests
__all__ = ["register", "_zip_with_secret"]
