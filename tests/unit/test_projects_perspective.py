"""Project and Perspective tool tests."""

from __future__ import annotations

from ignition_mcp.tools import perspective, projects

MINIMAL_VIEW = {"root": {"type": "ia.container.flex", "meta": {"name": "root"}}}
VIEWS_PREFIX = "Demo/com.inductiveautomation.perspective/views"


def test_project_list_happy(app_ctx, mock_client, make_tools):
    mock_client.get_json.return_value = {"items": [{"name": "P1"}]}
    tools = make_tools(projects)
    result = tools["project_list"]()
    assert result["projects"][0]["name"] == "P1"
    mock_client.get_json.assert_called_once_with("projects/list")


def test_project_create_requires_confirm(app_ctx, make_tools):
    tools = make_tools(projects)
    result = tools["project_create"](name="Demo")
    assert result["error"] == "write_not_allowed"


def test_project_create_bad_name(app_ctx, make_tools):
    tools = make_tools(projects)
    result = tools["project_create"](name="bad name!", confirm=True)
    assert result["error"] == "validation_error"


def test_project_delete_requires_name_echo(app_ctx, make_tools):
    tools = make_tools(projects)
    result = tools["project_delete"](name="Demo", confirm_name="Wrong", confirm=True)
    assert result["error"] == "validation_error"


def test_project_delete_happy(app_ctx, mock_client, make_tools):
    mock_client.delete_json.return_value = None
    tools = make_tools(projects)
    result = tools["project_delete"](name="Demo", confirm_name="Demo", confirm=True)
    assert result["deleted"] == "Demo"
    mock_client.delete_json.assert_called_once_with("projects/Demo")


def test_project_scan(app_ctx, mock_client, make_tools):
    mock_client.scan_projects.return_value = {"status": "ok"}
    tools = make_tools(projects)
    result = tools["project_scan"]()
    assert result["scan"] == "requested"


def test_list_views_strips_paths(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = {
        "entries": [
            {"path": f"{VIEWS_PREFIX}/Home/view.json", "isDir": False, "size": 10},
            {"path": f"{VIEWS_PREFIX}/sub/Detail/view.json", "isDir": False, "size": 10},
            {"path": f"{VIEWS_PREFIX}/Home/resource.json", "isDir": False, "size": 5},
        ]
    }
    tools = make_tools(perspective)
    result = tools["perspective_list_views"](project="Demo")
    assert result["views"] == ["Home", "sub/Detail"]


def test_get_view_parses_json(app_ctx, mock_bridge, make_tools):
    mock_bridge.call.return_value = {"content": '{"root": {}}'}
    tools = make_tools(perspective)
    result = tools["perspective_get_view"](project="Demo", view_path="Home")
    assert result["view"] == {"root": {}}


def test_upsert_view_requires_confirm(app_ctx, make_tools):
    tools = make_tools(perspective)
    result = tools["perspective_upsert_view"](project="Demo", view_path="Home", view_json={})
    assert result["error"] == "write_not_allowed"


def test_upsert_view_rejects_traversal(app_ctx, make_tools):
    tools = make_tools(perspective)
    result = tools["perspective_upsert_view"](
        project="Demo", view_path="../evil", view_json=MINIMAL_VIEW, confirm=True
    )
    assert result["error"] == "validation_error"


def test_upsert_view_writes_and_scans(app_ctx, mock_client, mock_bridge, make_tools):
    mock_bridge.call.return_value = {}
    mock_client.scan_projects.return_value = {"scanActive": True}
    tools = make_tools(perspective)
    result = tools["perspective_upsert_view"](
        project="Demo", view_path="Home", view_json=MINIMAL_VIEW, confirm=True
    )
    assert result["deployed"] is True
    write_calls = [c for c in mock_bridge.call.call_args_list if c[0][0] == "files/write"]
    assert len(write_calls) == 2
    mock_client.scan_projects.assert_called_once()


def test_delete_view_requires_name_echo(app_ctx, make_tools):
    tools = make_tools(perspective)
    result = tools["perspective_delete_view"](
        project="Demo", view_path="Home", confirm_name="Nope", confirm=True
    )
    assert result["error"] == "validation_error"
