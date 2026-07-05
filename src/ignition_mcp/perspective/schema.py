"""Offline structural validation of Perspective view.json documents. Stdlib only."""

from __future__ import annotations

from typing import Any

BINDING_TYPES = ("property", "expression", "tag", "query", "expr-struct", "http", "tag-history")


def validate_view(view: object) -> list[str]:
    """Return a list of human-readable problems; empty list means structurally valid."""
    if not isinstance(view, dict):
        return ["view must be a JSON object"]

    problems: list[str] = []

    for key in ("params", "custom", "props"):
        if key in view and not isinstance(view[key], dict):
            problems.append(f"{key} must be an object when present")

    root = view.get("root")
    if root is None:
        problems.append("missing root container")
    else:
        _validate_component(root, "root", problems)

    return problems


def _validate_component(node: Any, path: str, problems: list[str]) -> None:
    if not isinstance(node, dict):
        problems.append(f"{path}: component must be an object")
        return

    node_type = node.get("type")
    if not isinstance(node_type, str) or not node_type:
        problems.append(f"{path}: missing type")
        node_type = ""

    meta = node.get("meta")
    if not isinstance(meta, dict) or not isinstance(meta.get("name"), str) or not meta.get("name"):
        problems.append(f"{path}: missing meta.name")

    children = node.get("children")
    if children is not None:
        if not isinstance(children, list):
            problems.append(f"{path}: children must be a list")
        else:
            if children and node_type and not node_type.startswith("ia.container."):
                problems.append(f"{path}: type {node_type} should not have children")
            seen: set[str] = set()
            for i, child in enumerate(children):
                _validate_component(child, f"{path}/children[{i}]", problems)
                if isinstance(child, dict) and isinstance(child.get("meta"), dict):
                    name = child["meta"].get("name")
                    if isinstance(name, str) and name:
                        if name in seen:
                            problems.append(f"{path}: duplicate child name '{name}'")
                        seen.add(name)

    prop_config = node.get("propConfig")
    if isinstance(prop_config, dict):
        for key, value in prop_config.items():
            if isinstance(value, dict) and isinstance(value.get("binding"), dict):
                binding_type = value["binding"].get("type")
                if binding_type not in BINDING_TYPES:
                    problems.append(
                        f"{path}: propConfig {key} has unknown binding type {binding_type}"
                    )


def validate_page_config(config: object) -> list[str]:
    """Page config must be {'pages': {'/url': {'viewPath': str}, ...}}."""
    if not isinstance(config, dict):
        return ["config must be a JSON object"]

    pages = config.get("pages")
    if not isinstance(pages, dict):
        return ["config must contain 'pages' as an object"]

    problems: list[str] = []
    for url, value in pages.items():
        if not isinstance(url, str) or not url.startswith("/"):
            problems.append(f"page URL '{url}' must start with /")
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("viewPath"), str)
            or not value["viewPath"]
        ):
            problems.append(f"page '{url}' must contain 'viewPath' as a non-empty string")
    return problems
