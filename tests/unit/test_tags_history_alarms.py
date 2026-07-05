"""Tag, history, and alarm tool tests."""

from __future__ import annotations

from ignition_mcp.app import AppContext
from ignition_mcp.tools import alarms, history, tags


def test_tag_browse_calls_bridge(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = {"results": []}
    tools = make_tools(tags)
    result = tools["tag_browse"](path="Folder", provider="default", depth=2)
    assert result["results"] == []
    mock_bridge.call.assert_called_once_with(
        "tags/browse", {"path": "Folder", "provider": "default", "depth": 2}
    )


def test_tag_browse_rejects_bad_depth(app_ctx, make_tools):
    tools = make_tools(tags)
    result = tools["tag_browse"](depth=9)
    assert result["error"] == "validation_error"


def test_tag_read_happy(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = [{"path": "[default]A", "value": 5}]
    tools = make_tools(tags)
    result = tools["tag_read"](paths=["[default]A"])
    assert result["tags"][0]["value"] == 5


def test_tag_read_rejects_empty(app_ctx, make_tools):
    tools = make_tools(tags)
    result = tools["tag_read"](paths=[])
    assert result["error"] == "validation_error"


def test_tag_write_happy(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = [{"path": "[default]A", "quality": "Good"}]
    tools = make_tools(tags)
    result = tools["tag_write"](writes=[{"path": "[default]A", "value": 1}], confirm=True)
    assert result["results"][0]["quality"] == "Good"


def test_tag_write_refused_without_confirm(app_ctx, make_tools):
    tools = make_tools(tags)
    result = tools["tag_write"](writes=[{"path": "[default]A", "value": 2}])
    assert result["error"] == "write_not_allowed"


def test_tag_write_readonly_settings(settings_readonly, mock_client, mock_bridge, make_tools):
    ctx = AppContext(settings=settings_readonly, client=mock_client, bridge=mock_bridge)
    ctx.trial_warning = lambda: None  # type: ignore[method-assign]
    tools = make_tools(tags, ctx=ctx)
    result = tools["tag_write"](writes=[{"path": "[default]A", "value": 2}], confirm=True)
    assert result["error"] == "write_not_allowed"


def test_tag_config_import_bad_policy(app_ctx, make_tools):
    tools = make_tools(tags)
    result = tools["tag_config_import"](
        provider="default", base_path="", tags_json={}, collision_policy="destroy", confirm=True
    )
    assert result["error"] == "validation_error"


def test_history_query_happy(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = {"columns": ["t"], "rows": []}
    tools = make_tools(history)
    result = tools["history_query"](paths=["[default]A"], start="-8h")
    assert result["data"]["columns"] == ["t"]
    assert mock_bridge.call.call_count == 1
    assert mock_bridge.call.call_args[0][0] == "history/query"


def test_history_query_bad_aggregation(app_ctx, make_tools):
    tools = make_tools(history)
    result = tools["history_query"](paths=["[default]A"], start="-8h", aggregation="Median")
    assert result["error"] == "validation_error"


def test_history_query_too_many_paths(app_ctx, make_tools):
    tools = make_tools(history)
    result = tools["history_query"](paths=[f"[default]T{i}" for i in range(21)], start="-8h")
    assert result["error"] == "validation_error"


def test_alarm_status_happy(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = [{"id": "x"}]
    tools = make_tools(alarms)
    result = tools["alarm_status"]()
    assert result["alarms"] == [{"id": "x"}]


def test_alarm_status_bad_state(app_ctx, make_tools):
    tools = make_tools(alarms)
    result = tools["alarm_status"](states=["Bogus"])
    assert result["error"] == "validation_error"


def test_alarm_acknowledge_requires_confirm(app_ctx, make_tools):
    tools = make_tools(alarms)
    result = tools["alarm_acknowledge"](event_ids=["u1"])
    assert result["error"] == "write_not_allowed"
