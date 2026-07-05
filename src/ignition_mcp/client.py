"""GatewayClient — the only module that talks HTTP to the Ignition REST plane.

All tools go through these methods. Never construct httpx calls in tool modules.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .errors import (
    AuthError,
    GatewayError,
    NotFoundError,
    PermissionDeniedError,
)

API = "/data/api/v1"


class GatewayClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http = httpx.Client(
            base_url=settings.gateway_url,
            headers={"X-Ignition-API-Token": settings.api_token},
            verify=settings.tls_verify,
            timeout=settings.timeout_s,
        )

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ core

    def _check(self, resp: httpx.Response, context: str) -> httpx.Response:
        if resp.status_code == 401:
            raise AuthError()
        if resp.status_code == 403:
            raise PermissionDeniedError()
        if resp.status_code == 404:
            raise NotFoundError(f"Not found: {context}")
        if resp.status_code >= 500:
            raise GatewayError(
                f"Gateway error {resp.status_code} on {context}: {resp.text[:300]}",
                remediation="Check gateway logs (gateway_logs_query) for details.",
            )
        if resp.status_code >= 400:
            raise GatewayError(f"Unexpected {resp.status_code} on {context}: {resp.text[:300]}")
        return resp

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET a REST-plane path (relative to /data/api/v1 unless absolute) and parse JSON.
        Retries once on transient transport errors."""
        url = path if path.startswith("/") else f"{API}/{path}"
        last_exc: Exception | None = None
        for _attempt in range(2):
            try:
                resp = self._http.get(url, params=params)
                return self._json(self._check(resp, url))
            except httpx.TransportError as exc:  # connect/read errors only — idempotent GET
                last_exc = exc
        raise GatewayError(
            f"Cannot reach gateway at {self._settings.gateway_url}: {last_exc}",
            remediation="Confirm the gateway is running and IGNITION_URL is correct.",
        )

    def post_json(self, path: str, body: Any = None, params: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("/") else f"{API}/{path}"
        try:
            resp = self._http.post(url, json=body, params=params)
        except httpx.TransportError as exc:
            raise GatewayError(
                f"Cannot reach gateway at {self._settings.gateway_url}: {exc}",
                remediation="Confirm the gateway is running and IGNITION_URL is correct.",
            ) from exc
        return self._json(self._check(resp, url))

    def put_json(self, path: str, body: Any = None) -> Any:
        url = path if path.startswith("/") else f"{API}/{path}"
        try:
            resp = self._http.put(url, json=body)
        except httpx.TransportError as exc:
            raise GatewayError(f"Cannot reach gateway: {exc}") from exc
        return self._json(self._check(resp, url))

    def delete_json(self, path: str) -> Any:
        url = path if path.startswith("/") else f"{API}/{path}"
        try:
            resp = self._http.delete(url)
        except httpx.TransportError as exc:
            raise GatewayError(f"Cannot reach gateway: {exc}") from exc
        return self._json(self._check(resp, url))

    def get_bytes(self, path: str, params: dict[str, Any] | None = None) -> bytes:
        url = path if path.startswith("/") else f"{API}/{path}"
        resp = self._http.get(url, params=params)
        return self._check(resp, url).content

    def post_bytes(
        self, path: str, content: bytes, content_type: str, params: dict[str, Any] | None = None
    ) -> Any:
        url = path if path.startswith("/") else f"{API}/{path}"
        resp = self._http.post(
            url, content=content, params=params, headers={"Content-Type": content_type}
        )
        return self._json(self._check(resp, url))

    @staticmethod
    def _json(resp: httpx.Response) -> Any:
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    # ------------------------------------------------- shared high-level ops

    def status_ping(self) -> dict[str, Any]:
        """Unauthenticated liveness probe."""
        resp = self._http.get("/StatusPing")
        return self._json(self._check(resp, "/StatusPing")) or {}

    def trial_status(self) -> dict[str, Any]:
        result = self.get_json("trial")
        return result if isinstance(result, dict) else {}

    def scan_projects(self) -> Any:
        return self.post_json("scan/projects")

    def scan_config(self) -> Any:
        return self.post_json("scan/config")
