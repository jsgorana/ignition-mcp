"""Environment-driven configuration with fail-fast validation."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    gateway_url: str
    api_token: str
    bridge_secret: str | None = None
    allow_writes: bool = False
    tls_verify: bool = True
    timeout_s: float = 30.0
    tag_write_allowlist: tuple[str, ...] = field(default_factory=tuple)

    @property
    def bridge_enabled(self) -> bool:
        return self.bridge_secret is not None

    def tag_write_allowed(self, tag_path: str) -> bool:
        """True when no allowlist is set, or the path matches one of its globs."""
        if not self.tag_write_allowlist:
            return True
        return any(fnmatch.fnmatch(tag_path, pattern) for pattern in self.tag_write_allowlist)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings(environ: dict[str, str] | None = None) -> Settings:
    """Build Settings from environment variables. Raises ValueError listing every
    missing/invalid variable at once so users fix their config in one pass."""
    env = environ if environ is not None else dict(os.environ)
    problems: list[str] = []

    gateway_url = env.get("IGNITION_URL", "").strip().rstrip("/")
    if not gateway_url:
        problems.append("IGNITION_URL is required (e.g. http://localhost:8088)")
    elif not gateway_url.startswith(("http://", "https://")):
        problems.append("IGNITION_URL must start with http:// or https://")

    api_token = env.get("IGNITION_API_TOKEN", "").strip()
    if not api_token:
        problems.append("IGNITION_API_TOKEN is required (format: '<name>:<secret>')")
    elif ":" not in api_token:
        problems.append("IGNITION_API_TOKEN must have the form '<name>:<secret>'")

    timeout_raw = env.get("IGNITION_TIMEOUT_S", "30")
    try:
        timeout_s = float(timeout_raw)
        if timeout_s <= 0:
            raise ValueError
    except ValueError:
        problems.append(f"IGNITION_TIMEOUT_S must be a positive number, got {timeout_raw!r}")
        timeout_s = 30.0

    if problems:
        raise ValueError("Invalid ignition-mcp configuration:\n  - " + "\n  - ".join(problems))

    allowlist_raw = env.get("IGNITION_TAG_WRITE_ALLOWLIST", "").strip()
    allowlist = (
        tuple(p.strip() for p in allowlist_raw.split(",") if p.strip()) if allowlist_raw else ()
    )

    bridge_secret = env.get("IGNITION_BRIDGE_SECRET", "").strip() or None

    return Settings(
        gateway_url=gateway_url,
        api_token=api_token,
        bridge_secret=bridge_secret,
        allow_writes=_env_bool("IGNITION_ALLOW_WRITES", False),
        tls_verify=_env_bool("IGNITION_TLS_VERIFY", True),
        timeout_s=timeout_s,
        tag_write_allowlist=allowlist,
    )
