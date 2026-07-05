"""Error taxonomy for ignition-mcp.

Every tool maps transport/gateway failures into one of these classes. Each error
carries a machine-readable code, a human message, and a remediation hint that the
MCP client (an AI assistant) can act on or relay to the user.
"""

from __future__ import annotations


class IgnitionMcpError(Exception):
    """Base class. Never raised directly by tools."""

    code = "ignition_error"

    def __init__(self, message: str, remediation: str = "") -> None:
        self.message = message
        self.remediation = remediation
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {
            "error": self.code,
            "message": self.message,
            "remediation": self.remediation,
        }


class AuthError(IgnitionMcpError):
    """401 — the API token was rejected outright."""

    code = "auth_failed"

    def __init__(self, message: str = "Gateway rejected the API token (HTTP 401).") -> None:
        super().__init__(
            message,
            remediation=(
                "Check IGNITION_API_TOKEN has the form '<name>:<secret>' and that the key is "
                "enabled under Gateway > Platform > Security > API Keys."
            ),
        )


class PermissionDeniedError(IgnitionMcpError):
    """403 — authenticated, but the key's security level lacks access."""

    code = "permission_denied"

    def __init__(
        self, message: str = "Gateway denied access for this API token (HTTP 403)."
    ) -> None:
        super().__init__(
            message,
            remediation=(
                "The API key authenticates but lacks permission. In Gateway > Platform > "
                "Security > General, add the key's auto-created security level "
                "(Authenticated/<key-name>) to both 'Gateway Read Permissions' and "
                "'Gateway Write Permissions' (AnyOf), then retry. Run the "
                "ignition_diagnose tool for a guided check."
            ),
        )


class NotFoundError(IgnitionMcpError):
    """404 or a named object that does not exist."""

    code = "not_found"


class BridgeUnavailableError(IgnitionMcpError):
    """The WebDev bridge is not installed, not reachable, or the secret is wrong."""

    code = "bridge_unavailable"

    def __init__(
        self, message: str = "The mcp-bridge WebDev project is not available on the gateway."
    ) -> None:
        super().__init__(
            message,
            remediation=(
                "This capability requires the gateway-side bridge. Install it with the "
                "bridge_install tool (writes must be enabled), or see docs/bridge.md. "
                "Also confirm IGNITION_BRIDGE_SECRET matches the secret configured in the bridge."
            ),
        )


class TrialExpiredError(IgnitionMcpError):
    """The gateway trial period has expired; runtime features are paused."""

    code = "trial_expired"

    def __init__(self, message: str = "The gateway's 2-hour trial has expired.") -> None:
        super().__init__(
            message,
            remediation=(
                "Reset the trial with the gateway_trial_reset tool (requires the bridge), or click "
                "'Reset Trial' on the gateway homepage."
            ),
        )


class ValidationError(IgnitionMcpError):
    """Tool input failed validation before any gateway call."""

    code = "validation_error"


class WriteNotAllowedError(IgnitionMcpError):
    """A mutating tool was called without writes enabled or without confirm."""

    code = "write_not_allowed"


class GatewayError(IgnitionMcpError):
    """5xx or unexpected gateway response."""

    code = "gateway_error"
