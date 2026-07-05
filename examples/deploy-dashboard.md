# Example: deploy a Perspective dashboard from a prompt

This transcript shows the full round-trip that `ignition-mcp` performs. It assumes the bridge is
installed and the server runs with `IGNITION_ALLOW_WRITES=true`.

---

**You:**
> Create a Perspective project called `LineOverview` with a dashboard at `/` showing the value of
> `[default]McpDemo/Value1` in a large label and a gauge bound to `[default]McpDemo/Value2`.

**Assistant** (calls `perspective_bootstrap_project`):

```json
{ "project": "LineOverview", "title": "Line Overview", "confirm": true }
```

→ project created, `Home` view seeded, `/` mapped, scan requested.

**Assistant** (reads `ignition://templates/view/tag-bound-dashboard`, adapts it, then calls
`perspective_validate_view` to be safe):

```json
{ "valid": true, "problems": [] }
```

**Assistant** (calls `perspective_upsert_view`):

```json
{
  "project": "LineOverview",
  "view_path": "Home",
  "confirm": true,
  "view_json": {
    "props": { "defaultSize": { "height": 600, "width": 800 } },
    "params": {}, "custom": {},
    "root": {
      "type": "ia.container.flex",
      "meta": { "name": "root" },
      "props": { "direction": "column" },
      "children": [
        {
          "type": "ia.display.label",
          "meta": { "name": "Value1" },
          "position": { "basis": "80px" },
          "props": { "text": "", "style": { "fontSize": "48px" } },
          "propConfig": {
            "props.text": {
              "binding": { "type": "tag",
                "config": { "mode": "direct", "tagPath": "[default]McpDemo/Value1" } }
            }
          }
        },
        {
          "type": "ia.display.gauge",
          "meta": { "name": "Value2" },
          "position": { "grow": 1, "basis": "auto" },
          "props": { "value": 0, "outerAxis": { "range": { "low": 0, "high": 100 } } },
          "propConfig": {
            "props.value": {
              "binding": { "type": "tag",
                "config": { "mode": "direct", "tagPath": "[default]McpDemo/Value2" } }
            }
          }
        }
      ]
    }
  }
}
```

→ `{ "deployed": true, "scan": { "scanActive": true } }`

**Assistant:**
> Done. Your dashboard is live at
> `http://localhost:8088/data/perspective/client/LineOverview`. The label shows Value1 and the
> gauge is bound to Value2, ranged 0 to 100.

---

## Reproducing headlessly

The live integration suite (`tests/live/live_check.py`) runs exactly this round trip
programmatically: bootstrap, upsert a view with a tag binding, confirm the client page returns
HTTP 200, delete the view, export, delete the project. Run it against a scratch gateway:

```bash
IGNITION_URL=http://localhost:8088 \
IGNITION_API_TOKEN='claude:...' \
IGNITION_BRIDGE_SECRET='...' \
IGNITION_ALLOW_WRITES=true \
python tests/live/live_check.py
```
