"""Shared fixtures for ignition-mcp unit tests. No network, no real gateway."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, create_autospec

import pytest

from ignition_mcp.app import AppContext
from ignition_mcp.bridge import BridgeClient
from ignition_mcp.client import GatewayClient
from ignition_mcp.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gateway_url="http://gw:8088",
        api_token="claude:x",
        bridge_secret="testsecret",
        allow_writes=True,
    )


@pytest.fixture
def settings_readonly() -> Settings:
    return Settings(
        gateway_url="http://gw:8088",
        api_token="claude:x",
        bridge_secret="testsecret",
        allow_writes=False,
    )


@pytest.fixture
def mock_client() -> MagicMock:
    return create_autospec(GatewayClient, instance=True)


@pytest.fixture
def mock_bridge() -> MagicMock:
    bridge = create_autospec(BridgeClient, instance=True)
    bridge.enabled = True
    return bridge


@pytest.fixture
def app_ctx(settings: Settings, mock_client: MagicMock, mock_bridge: MagicMock) -> AppContext:
    ctx = AppContext(settings=settings, client=mock_client, bridge=mock_bridge)
    ctx.trial_warning = lambda: None  # type: ignore[method-assign]
    return ctx


class FakeMCP:
    """Minimal FastMCP stand-in that records registered tools/resources by name."""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}
        self.resources: dict[str, Callable[..., Any]] = {}

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(
        self, uri: str, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.resources[uri] = fn
            return fn

        return decorator


@pytest.fixture
def make_tools(app_ctx: AppContext) -> Callable[[Any], dict[str, Callable[..., Any]]]:
    """Register a tool module against a FakeMCP and return its tools by name.

    Modules exposing register_extra (perspective part 2) get both registered.
    """

    def factory(module: Any, ctx: AppContext | None = None) -> dict[str, Callable[..., Any]]:
        fake = FakeMCP()
        target_ctx = ctx if ctx is not None else app_ctx
        module.register(fake, target_ctx)
        if hasattr(module, "register_extra"):
            module.register_extra(fake, target_ctx)
        return fake.tools

    return factory
