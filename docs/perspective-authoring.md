# Authoring & deploying Perspective views

`ignition-mcp` can create and deploy Perspective views end-to-end. This doc explains how the
pieces fit so both humans and AI assistants produce valid views on the first try.

## The deployment model

A Perspective view is stored on the gateway as files under a project:

```
data/projects/<project>/com.inductiveautomation.perspective/views/<view-path>/
  ├── view.json        # the view definition
  └── resource.json    # Ignition resource manifest
```

`ignition-mcp` writes these through the bridge's file endpoints and then triggers a project scan
(`POST /data/api/v1/scan/projects`), which makes the gateway adopt the change live. No gateway
restart, no Designer needed.

## The workflow

1. Read the schema. The assistant reads the MCP resource `ignition://docs/view-schema` for the
   exact structure and component/binding rules.
2. Start from a template. `ignition://templates/view/flex-basic`, `.../coordinate-basic`, and
   `.../tag-bound-dashboard` are known-good starting points.
3. Validate offline. `perspective_validate_view(view_json=...)` checks structure locally
   (required keys, component `type`/`meta.name`, unique sibling names, container-only children,
   valid binding types) without a gateway round trip.
4. Deploy. `perspective_upsert_view(project, view_path, view_json, confirm=true)` re-validates,
   writes `view.json` and `resource.json`, and scans. It returns once the scan is requested.
5. Wire a page, optionally. `perspective_page_config_set(project, page_url, view_path)` maps a
   URL like `/overview` to the view. It reads, modifies, and writes the page config, so existing
   pages are never clobbered.
6. View it. The live client is served at `http://<gateway>/data/perspective/client/<project>`.
   Allow a couple of seconds after project creation for Perspective to mount a brand-new project.

## Bootstrapping a whole app in one call

`perspective_bootstrap_project(project, title, confirm=true)` creates the project, seeds a
starter `Home` view, maps it to `/`, and scans, giving you a working Perspective app from a
single tool call. Add more views with `perspective_upsert_view` afterward.

## view.json cheat-sheet

```json
{
  "props": { "defaultSize": { "height": 600, "width": 800 } },
  "params": {},
  "custom": {},
  "root": {
    "type": "ia.container.flex",
    "meta": { "name": "root" },
    "props": { "direction": "column" },
    "children": [
      {
        "type": "ia.display.label",
        "meta": { "name": "Speed" },
        "position": { "basis": "auto" },
        "props": { "text": "" },
        "propConfig": {
          "props.text": {
            "binding": {
              "type": "tag",
              "config": { "mode": "direct", "tagPath": "[default]Line1/Speed" }
            }
          }
        }
      }
    ]
  }
}
```

Rules that the validator enforces:

- `root` is required and is a component (`type` + `meta.name`).
- Every component needs `type` and `meta.name`.
- Sibling components need unique `meta.name` values.
- Only `ia.container.*` components may have `children`.
- Binding `type` must be one of: `property`, `expression`, `tag`, `query`, `expr-struct`,
  `http`, `tag-history`.

## Common component types

| type | purpose |
|---|---|
| `ia.container.flex` | flexbox container (`direction`, `justify`, `alignItems`) |
| `ia.container.coord` | coordinate container (absolute positioning) |
| `ia.display.label` | text |
| `ia.display.gauge` | radial gauge (`value`, `outerAxis.range`) |
| `ia.display.led-display` | numeric LED |
| `ia.chart.timeseries` | time-series chart |
| `ia.input.button` / `ia.input.numeric-entry-field` / `ia.input.text-field` | inputs |
| `ia.display.table` | data table |

See [examples/deploy-dashboard.md](../examples/deploy-dashboard.md) for a complete transcript.
