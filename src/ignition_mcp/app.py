"""Application context and the tool_result wrapper shared by all tool modules."""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from .bridge import BridgeClient
from .client import GatewayClient
from .config import Settings
from .errors import IgnitionMcpError

F = TypeVar("F", bound=Callable[..., Any])

TRIAL_WARN_SECONDS = 300
_TRIAL_CACHE_TTL = 60.0


@dataclass
class AppContext:
    settings: Settings
    client: GatewayClient
    bridge: BridgeClient
    _trial_cache: dict[str, Any] = field(default_factory=dict)
    _trial_cache_at: float = 0.0

    def trial_snapshot(self) -> dict[str, Any]:
        """Trial status with a 60s cache so per-tool enrichment stays cheap."""
        now = time.monotonic()
        if now - self._trial_cache_at > _TRIAL_CACHE_TTL:
            try:
                self._trial_cache = self.client.trial_status()
            except IgnitionMcpError:
                self._trial_cache = {}
            self._trial_cache_at = now
        return self._trial_cache

    def trial_warning(self) -> str | None:
        snap = self.trial_snapshot()
        if not snap or snap.get("licenseMode") != "Trial":
            return None
        if snap.get("expired"):
            return "GATEWAY TRIAL EXPIRED — runtime features are paused. Use gateway_trial_reset."
        seconds = snap.get("trialSecondsLeft")
        if isinstance(seconds, (int, float)) and seconds < TRIAL_WARN_SECONDS:
            return f"Gateway trial expires in {int(seconds)}s. Consider gateway_trial_reset."
        return None


def tool_result(ctx: AppContext) -> Callable[[F], F]:
    """Decorator for every tool function:
    - maps IgnitionMcpError to a structured error dict (never a stack trace)
    - appends trial_warning when the trial is about to expire (FR-D5)
    """

    def decorate(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = fn(*args, **kwargs)
            except IgnitionMcpError as exc:
                return exc.to_dict()
            warning = ctx.trial_warning()
            if warning and isinstance(result, dict) and "trial_warning" not in result:
                result["trial_warning"] = warning
            return result

        return wrapper  # type: ignore[return-value]

    return decorate
