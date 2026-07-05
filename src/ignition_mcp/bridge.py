"""BridgeClient — HMAC-authenticated client for the mcp-bridge WebDev project.

Transport: POST to /system/webdev/mcp-bridge/api/<endpoint> with a signed envelope:

    {"ts": "<unix seconds>", "sig": "<hex hmac-sha256(secret, ts + '.' + payload)>",
     "payload": "<json-encoded string of the actual request payload>"}

The payload travels as a string so the gateway verifies the HMAC over the exact bytes
it received — no JSON canonicalization ambiguity. The bridge rejects timestamp skew
greater than 300 seconds.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from .config import Settings
from .errors import BridgeUnavailableError, GatewayError

BRIDGE_BASE = "/system/webdev/mcp-bridge/api"
MIN_BRIDGE_VERSION = "0.1.0"


def sign(secret: str, timestamp: str, payload: str) -> str:
    msg = (timestamp + "." + payload).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


class BridgeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http = httpx.Client(
            base_url=settings.gateway_url,
            verify=settings.tls_verify,
            timeout=settings.timeout_s,
        )

    def close(self) -> None:
        self._http.close()

    @property
    def enabled(self) -> bool:
        return self._settings.bridge_enabled

    def call(self, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
        """POST a signed envelope to a bridge endpoint. Raises BridgeUnavailableError
        when the bridge is not configured, not installed, or rejects authentication."""
        if not self._settings.bridge_secret:
            raise BridgeUnavailableError(
                "IGNITION_BRIDGE_SECRET is not set, so bridge capabilities are disabled."
            )
        payload_str = json.dumps(payload or {})
        ts = str(int(time.time()))
        envelope = {
            "ts": ts,
            "sig": sign(self._settings.bridge_secret, ts, payload_str),
            "payload": payload_str,
        }
        try:
            resp = self._http.post(f"{BRIDGE_BASE}/{endpoint}", json=envelope)
        except httpx.TransportError as exc:
            raise GatewayError(f"Cannot reach gateway: {exc}") from exc

        if resp.status_code == 404:
            raise BridgeUnavailableError()
        if resp.status_code >= 400:
            raise GatewayError(f"Bridge error {resp.status_code} on {endpoint}: {resp.text[:300]}")

        data = resp.json() if resp.content else {}
        if isinstance(data, dict) and data.get("ok") is False:
            error = str(data.get("error", "unknown error"))
            if data.get("code") == "auth":
                if "not configured" in error:
                    raise BridgeUnavailableError(
                        "The bridge is still running with its placeholder secret. This is a "
                        "known issue where Ignition does not hot-reload a script-python module "
                        "after `projects/import` (a full gateway restart does not fix it either). "
                        "Fix: edit data/projects/mcp-bridge/ignition/script-python/mcp_bridge_lib/"
                        "code.py directly (replace BRIDGE_SECRET), then POST "
                        "/data/api/v1/scan/projects — a raw filesystem write reliably triggers "
                        "the reload. See docs/bridge.md#troubleshooting."
                    )
                raise BridgeUnavailableError(
                    "The bridge rejected authentication — IGNITION_BRIDGE_SECRET does not "
                    "match the secret configured in the mcp-bridge project."
                )
            raise GatewayError(
                f"Bridge endpoint {endpoint} failed: {error}",
                remediation=str(data.get("remediation", "")),
            )
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

    def ping(self) -> dict[str, Any]:
        """Returns {'version': ..., 'capabilities': [...]} from the bridge."""
        result = self.call("ping")
        return result if isinstance(result, dict) else {"version": "unknown"}
