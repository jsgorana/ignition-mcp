"""Connection & diagnostics tools (FR-D1..FR-D4).

GOLD-STANDARD MODULE: every other tool module follows this exact shape —
a register(mcp, ctx) function, @mcp.tool() functions wrapped by tool_result(ctx),
thin bodies that validate, guard, call the client, and shape a dict.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..app import AppContext, tool_result
from ..errors import (
    AuthError,
    BridgeUnavailableError,
    GatewayError,
    IgnitionMcpError,
    PermissionDeniedError,
)
from ..guards import require_writes


def register(mcp: FastMCP, ctx: AppContext) -> None:
    @mcp.tool()
    @tool_result(ctx)
    def gateway_info() -> dict[str, Any]:
        """Gateway version, edition, uptime, and health overview. Read-only, REST plane."""
        info = ctx.client.get_json("gateway-info")
        overview = ctx.client.get_json("overview")
        return {"gateway": info, "overview": overview}

    @mcp.tool()
    @tool_result(ctx)
    def gateway_trial_status() -> dict[str, Any]:
        """Trial/license state including seconds remaining. Read-only, REST plane."""
        return ctx.client.trial_status()

    @mcp.tool()
    @tool_result(ctx)
    def gateway_trial_reset(confirm: bool = False) -> dict[str, Any]:
        """Reset the gateway's 2-hour trial timer (trial gateways only). Mutating, bridge plane."""
        require_writes(ctx.settings, confirm, "gateway_trial_reset")
        result = ctx.bridge.call("trial/reset")
        status = ctx.client.trial_status()
        return {"reset": result, "trial": status}

    @mcp.tool()
    def ignition_diagnose() -> dict[str, Any]:
        """Guided health check: reachability, token, permissions, bridge, trial.
        Read-only. Run this first when anything misbehaves."""
        checks: list[dict[str, str]] = []

        def check(name: str, status: str, detail: str, remediation: str = "") -> None:
            item = {"check": name, "status": status, "detail": detail}
            if remediation:
                item["remediation"] = remediation
            checks.append(item)

        # 1. Reachability (unauthenticated)
        try:
            state = ctx.client.status_ping().get("state", "UNKNOWN")
            check("reachability", "ok", f"Gateway responds, state={state}")
        except IgnitionMcpError as exc:
            check("reachability", "fail", exc.message, exc.remediation)
            return {"checks": checks, "healthy": False}

        # 2 + 3. Token validity and permission level
        try:
            ctx.client.get_json("gateway-info")
            check("api_token", "ok", "Token authenticates and has read permission")
        except AuthError as exc:
            check("api_token", "fail", exc.message, exc.remediation)
            return {"checks": checks, "healthy": False}
        except PermissionDeniedError as exc:
            token_name = ctx.settings.api_token.split(":", 1)[0]
            check(
                "api_permissions",
                "fail",
                "Token authenticates (401 would mean bad token) but gets 403 on read routes.",
                f"In Gateway > Platform > Security > General, add security level "
                f"'Authenticated/{token_name}' to Gateway Read Permissions and Gateway Write "
                f"Permissions (AnyOf). {exc.remediation}",
            )
            return {"checks": checks, "healthy": False}

        # 4. Bridge
        if not ctx.settings.bridge_enabled:
            check(
                "bridge",
                "warn",
                "IGNITION_BRIDGE_SECRET not set — live tags, history, alarms, Perspective "
                "deployment and trial reset are disabled.",
                "Install the mcp-bridge project and set IGNITION_BRIDGE_SECRET (docs/bridge.md).",
            )
        else:
            try:
                pong = ctx.bridge.ping()
                check("bridge", "ok", f"Bridge v{pong.get('version', '?')} responding")
            except BridgeUnavailableError as exc:
                check("bridge", "fail", exc.message, exc.remediation)
            except GatewayError as exc:
                check("bridge", "fail", exc.message, exc.remediation)

        # 5. Trial state
        try:
            trial = ctx.client.trial_status()
            if trial.get("licenseMode") != "Trial":
                check("license", "ok", f"License mode: {trial.get('licenseMode', 'unknown')}")
            elif trial.get("expired"):
                check(
                    "license",
                    "fail",
                    "Trial EXPIRED — runtime features paused.",
                    "Run gateway_trial_reset or click Reset Trial on the gateway homepage.",
                )
            else:
                check(
                    "license",
                    "ok",
                    f"Trial active, {trial.get('trialSecondsLeft', '?')}s remaining",
                )
        except IgnitionMcpError as exc:
            check("license", "warn", exc.message, exc.remediation)

        # 6. Write posture (informational)
        check(
            "write_mode",
            "ok" if ctx.settings.allow_writes else "warn",
            "Writes ENABLED"
            if ctx.settings.allow_writes
            else "Read-only mode (IGNITION_ALLOW_WRITES not set) — mutating tools will refuse.",
        )

        healthy = all(c["status"] != "fail" for c in checks)
        return {"checks": checks, "healthy": healthy}
