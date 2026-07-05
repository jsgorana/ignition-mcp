"""Schema validation + gateway/database tool tests."""

from __future__ import annotations

from ignition_mcp.perspective.schema import validate_page_config, validate_view
from ignition_mcp.tools import database, gateway

VALID_VIEW = {
    "params": {},
    "props": {},
    "root": {
        "type": "ia.container.flex",
        "meta": {"name": "root"},
        "children": [
            {"type": "ia.display.label", "meta": {"name": "Label1"}, "props": {"text": "hi"}}
        ],
    },
}


def test_valid_flex_view_passes():
    assert validate_view(VALID_VIEW) == []


def test_non_dict_view_fails():
    assert validate_view("nope") == ["view must be a JSON object"]


def test_missing_root_fails():
    problems = validate_view({})
    assert any("root" in p for p in problems)


def test_component_missing_type():
    view = {"root": {"meta": {"name": "root"}, "children": [{"meta": {"name": "C1"}}]}}
    problems = validate_view(view)
    assert any("root/children[0]" in p and "type" in p for p in problems)


def test_duplicate_child_names():
    view = {
        "root": {
            "type": "ia.container.flex",
            "meta": {"name": "root"},
            "children": [
                {"type": "ia.display.label", "meta": {"name": "A"}},
                {"type": "ia.display.label", "meta": {"name": "A"}},
            ],
        }
    }
    problems = validate_view(view)
    assert any("duplicate child name 'A'" in p for p in problems)


def test_children_on_non_container():
    view = {
        "root": {
            "type": "ia.container.flex",
            "meta": {"name": "root"},
            "children": [
                {
                    "type": "ia.display.label",
                    "meta": {"name": "L"},
                    "children": [{"type": "ia.display.label", "meta": {"name": "X"}}],
                }
            ],
        }
    }
    problems = validate_view(view)
    assert any("should not have children" in p for p in problems)


def test_bad_binding_type():
    view = {
        "root": {
            "type": "ia.container.flex",
            "meta": {"name": "root"},
            "propConfig": {"props.text": {"binding": {"type": "telepathy"}}},
        }
    }
    problems = validate_view(view)
    assert any("binding" in p and "telepathy" in p for p in problems)


def test_page_config_rules():
    assert validate_page_config({"pages": {"noslash": {"viewPath": "Home"}}}) != []
    assert validate_page_config({"pages": {"/": {"viewPath": "Home"}}}) == []


def test_gateway_modules(app_ctx, mock_client, make_tools):
    mock_client.get_json.side_effect = [{"items": [{"name": "M"}]}, {"items": []}]
    tools = make_tools(gateway)
    result = tools["gateway_modules"]()
    assert result["modules"][0]["name"] == "M"


def test_logs_query_bad_level(app_ctx, make_tools):
    tools = make_tools(gateway)
    result = tools["gateway_logs_query"](level="LOUD")
    assert result["error"] == "validation_error"


def test_logger_set_level_requires_confirm(app_ctx, make_tools):
    tools = make_tools(gateway)
    result = tools["gateway_logger_set_level"](logger_name="tags", level="DEBUG")
    assert result["error"] == "write_not_allowed"


def test_db_query_select_is_readonly(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = {"columns": ["1"], "rows": [[1]]}
    tools = make_tools(database)
    result = tools["db_query"](sql="SELECT 1")
    assert result["mutating"] is False
    assert "error" not in result


def test_db_query_update_requires_confirm(app_ctx, make_tools):
    tools = make_tools(database)
    result = tools["db_query"](sql="UPDATE t SET x=1")
    assert result["error"] == "write_not_allowed"


def test_db_query_comment_prefix(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = {"columns": ["1"], "rows": [[1]]}
    tools = make_tools(database)
    result = tools["db_query"](sql="-- note\nSELECT 1")
    assert result["mutating"] is False
